#!/usr/bin/env python3
"""Cheap shared X11 utility preflight before build; NEVER native GPUI qualification."""
import argparse
import io
import json
import os
import secrets
import signal
import time
from pathlib import Path
from PIL import Image
from native_assertions import GateFailure, require, sha256
from native_driver import Owner
from display_session import DisplaySession, display_environment, wait_for, auth_denied

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir",type=Path,required=True)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    args = parser.parse_args()
    require(os.geteuid() != 0,"X11 preflight must not run as root")
    work,evidence = args.work_dir.resolve(),args.evidence_dir.resolve()
    require(not work.exists() and not evidence.exists(),"Fresh absent preflight directories required")
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    canceled = []
    for number in (signal.SIGTERM,signal.SIGINT):
        signal.signal(number,lambda number,frame:canceled.append(number))
    result = {"schema":1,"status":"running",
              "scope":"X11 infrastructure only; no Proteus binary or GPUI native qualification",
              "native_window_proven":False,"checks":[]}
    owner,display,clipboard = None,None,None
    try:
        env = display_environment(work)
        owner = Owner(env,time.monotonic()+90,canceled=lambda:bool(canceled))
        result["system_packages"] = owner.run(["dpkg-query","-W","xvfb","xauth","openbox",
                                                "dbus","x11-utils","x11-xserver-utils",
                                                "imagemagick","xclip","mesa-vulkan-drivers",
                                                "libgl1-mesa-dri","python3-pil"]).decode()
        display = DisplaySession(owner)
        display.start()
        result["checks"].append("shared-authenticated-display-and-window-manager")
        bad = dict(env,XAUTHORITY=str(work/"absent-auth-file"))
        owner.run(["xdpyinfo"],timeout=2,check=False,env=bad,record_output=True)
        denied = owner.commands[-1]
        require(denied["exit_code"] == 1 and not denied["stdout"] and auth_denied(denied["stderr"]),
                "Expected explicit X11 authentication denial was not observed")
        require(display.services[0][1].poll() is None,"Xvfb exited during authentication negative control")
        owner.run(["xdpyinfo"],timeout=5,record_output=True)
        result["checks"].append("unauthenticated-client-rejected-authenticated-client-accepted")
        owner.run(["xsetroot","-solid","#112233"])
        png = owner.run(["import","-window","root","-depth","8","png:-"],timeout=5,cap=5*1024*1024)
        image = Image.open(io.BytesIO(png)).convert("RGB")
        require(image.size == (1280,900),"Preflight root capture geometry differs")
        require(image.getpixel((10,10)) == (17,34,51),"Root capture did not reflect synthetic X11 color")
        (evidence/"infrastructure-root.png").write_bytes(png)
        result["capture"] = {"file":"infrastructure-root.png","sha256":sha256(png),
                             "bytes":len(png),"size":list(image.size),
                             "claim":"Synthetic root color only, not native application pixels"}
        result["checks"].append("real-root-pixel-capture")
        nonce = "X11-PREFLIGHT-"+secrets.token_hex(16)
        clipboard = owner.start("clipboard-preflight",
                                ["xclip","-selection","clipboard","-in","-quiet"],stdin=True)
        clipboard.stdin.write(nonce.encode())
        clipboard.stdin.close()
        def clipboard_ready():
            require(clipboard.poll() is None,"Preflight clipboard owner exited")
            text = owner.run(["xclip","-selection","clipboard","-out","-target","UTF8_STRING"],
                             timeout=2,check=False,cap=65536)
            return text.decode("utf-8") == nonce
        wait_for(owner,clipboard_ready,"synthetic CLIPBOARD utility roundtrip",seconds=5)
        result["checks"].append("external-clipboard-utilities-only")
        result["software_graphics"] = {
            "vulkaninfo":owner.run(["vulkaninfo","--summary"],timeout=15,record_output=True).decode(),
            "glxinfo":owner.run(["glxinfo","-B"],timeout=15,record_output=True).decode()}
        result["checks"].append("software-graphics-utility-probes-only")
        owner.check()
        result["status"] = "passed"
    except BaseException as exc:
        result["status"],result["error"] = "failed",type(exc).__name__+": "+str(exc)
        raise
    finally:
        if owner:
            if clipboard:
                owner.kill(clipboard)
                clipboard.wait(timeout=3)
            if display:
                try:
                    display.close()
                except BaseException as exc:
                    result["status"],result["error"] = "failed","Display cleanup: "+str(exc)
                result["display_infrastructure"] = display.receipt
            owner.close()
            if owner.fatal:
                result["status"],result["error"] = "failed",owner.fatal
            result["commands"] = owner.commands
            result["cleanup_error"] = owner.fatal
            for name,data in owner.logs.items():
                (evidence/(name+".log")).write_bytes(data)
        result["cancellation_signals"] = canceled
        data = (json.dumps(result,indent=2,sort_keys=True)+"\n").encode()
        require(len(data) <= 8*1024*1024,"Preflight JSON cap exceeded")
        (evidence/"result.json").write_bytes(data)
        require(result["status"] == "passed",result.get("error","X11 preflight did not pass"))

if __name__ == "__main__":
    main()
