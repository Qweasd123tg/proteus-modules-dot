"""Shared authenticated X11 infrastructure; never a native GPUI correctness oracle."""
import os
import re
import secrets
import signal
import subprocess
import time
from pathlib import Path
from native_assertions import GateFailure, UtilityTimeout, require

def wait_for(owner, predicate, label, seconds=15):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        owner.check()
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise GateFailure("Timed out: " + label)

def display_environment(work):
    env = {key:os.environ[key] for key in ("PATH",) if key in os.environ}
    env.update({"LANG":"C.UTF-8","LC_ALL":"C.UTF-8","TZ":"UTC",
                "DISPLAY":":99","XAUTHORITY":str(work/"Xauthority"),
                "XDG_RUNTIME_DIR":str(work/"xdg-runtime"),
                "HOME":str(work/"service-home"),"GPUI_X11_SCALE_FACTOR":"1",
                "LIBGL_ALWAYS_SOFTWARE":"true","GALLIUM_DRIVER":"llvmpipe",
                "NO_PROXY":"127.0.0.1,localhost,::1","no_proxy":"127.0.0.1,localhost,::1",
                "PROTEUS_STARTUP_TRACE":"1","PYTHONDONTWRITEBYTECODE":"1","npm_config_audit":"false"})
    Path(env["HOME"]).mkdir()
    Path(env["XDG_RUNTIME_DIR"]).mkdir(mode=0o700)
    icds = sorted(Path("/usr/share/vulkan/icd.d").glob("lvp_icd*.json"))
    require(len(icds) == 1,"Exactly one installed Lavapipe ICD is required")
    env["VK_DRIVER_FILES"] = str(icds[0])
    return env

def auth_denied(error):
    return re.search(r"authorization required|invalid.*cookie|no protocol specified",
                     error,re.I) is not None

def wait_x11(owner, xvfb, seconds=30, clock=time.monotonic, sleep=time.sleep, receipt=None):
    """Only startup-not-ready and typed per-probe timeout are retryable."""
    until = clock() + seconds
    receipt = receipt if receipt is not None else {}
    receipt.update(status="waiting",budget_seconds=seconds,xvfb_pid=getattr(xvfb,"pid",None))
    attempts = receipt.setdefault("attempts",[])
    while clock() < until and len(attempts) < 300:
        owner.check()
        require(xvfb.poll() is None,"Xvfb exited during readiness")
        timed_out = False
        try:
            output = owner.run(["xdpyinfo"],timeout=min(2,until-clock()),check=False,
                               record_output=True)
        except UtilityTimeout:
            output, timed_out = b"", True
        row = owner.commands[-1]
        attempts.append({"command_seq":len(owner.commands),"timed_out":timed_out,
                         "returncode":row.get("exit_code"),"at_ns":row.get("finished_ns"),
                         "xvfb_returncode":xvfb.poll()})
        require(xvfb.poll() is None,"Xvfb exited during readiness probe")
        require(clock() <= until,"Xvfb readiness exceeded its total deadline")
        error = row.get("stderr","")
        require(not auth_denied(error),"X11 authentication failed")
        if not timed_out and row.get("exit_code") == 0:
            require(output.startswith(b"name of display")
                    and re.search(rb"dimensions:\s+1280x900 pixels",output),
                    "Unexpected authenticated X11 display geometry/output")
            receipt["status"] = "ready"
            return receipt
        require(timed_out or row.get("exit_code") == 1,
                "Unexpected X11 readiness utility exit")
        sleep(min(0.1,max(0,until-clock())))
    raise GateFailure("Xvfb not ready within bounded startup protocol")

class DisplaySession:
    def __init__(self, owner):
        self.owner = owner
        self.services = []
        self.receipt = {"scope":"X11 infrastructure only, not native GPUI qualification"}
        self.closed = False

    def start(self):
        env = self.owner.env
        require(not Path("/tmp/.X99-lock").exists()
                and not Path("/tmp/.X11-unix/X99").exists(),"X display 99 is already in use")
        self.owner.run(["xauth","-f",env["XAUTHORITY"],"add",":99",
                        "MIT-MAGIC-COOKIE-1",secrets.token_hex(16)],record_output=True)
        xvfb = self.owner.start("xvfb",["Xvfb",":99","-screen","0","1280x900x24",
                                       "-nolisten","tcp","-auth",env["XAUTHORITY"],"-noreset"])
        self.services.append(("xvfb",xvfb))
        self.receipt["service_pids"] = {"xvfb":xvfb.pid}
        self.receipt["readiness"] = {}
        wait_x11(self.owner,xvfb,receipt=self.receipt["readiness"])
        dbus = self.owner.start("dbus",["dbus-daemon","--session","--nofork","--print-address=1"])
        self.services.append(("dbus",dbus))
        self.receipt["service_pids"]["dbus"] = dbus.pid
        address = wait_for(self.owner,lambda:bytes(self.owner.logs["dbus"]).splitlines(),
                           "D-Bus readiness")[0].decode()
        require(address.startswith("unix:"),"Unexpected D-Bus session address")
        env["DBUS_SESSION_BUS_ADDRESS"] = address
        wm = self.owner.start("openbox",["openbox","--sm-disable"],env=env)
        self.services.append(("openbox",wm))
        self.receipt["service_pids"]["openbox"] = wm.pid
        def wm_ready():
            require(wm.poll() is None,"Openbox exited during readiness")
            return b"window id" in self.owner.run(["xprop","-root","_NET_SUPPORTING_WM_CHECK"],
                                                 check=False,record_output=True)
        wait_for(self.owner,wm_ready,"Window manager readiness")
        self.receipt["service_pids"] = {name:process.pid for name,process in self.services}
        self.receipt["status"] = "ready"
        return self

    def close(self):
        if self.closed:
            return
        self.closed = True
        failures = []
        for name,process in reversed(self.services):
            if process.poll() is None:
                try:
                    os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.owner.kill(process)
                    process.wait(timeout=3)
                    failures.append(name+" required forced cleanup")
        # Successful preflight must leave a genuinely fresh display for the native stage.
        if self.services and (Path("/tmp/.X99-lock").exists() or Path("/tmp/.X11-unix/X99").exists()):
            failures.append("Owned X11 display lock/socket survived graceful cleanup")
        self.receipt["cleanup_errors"] = failures
        require(not failures,"; ".join(failures))
