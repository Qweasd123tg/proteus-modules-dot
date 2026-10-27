#!/usr/bin/env python3
"""Qualify external native behavior of the same-job reconstructed portable candidate."""
import argparse
import hashlib
import json
import os
import secrets
import signal
import stat
import time
import uuid
from pathlib import Path
from native_assertions import (GateFailure, require, marker, ordered, anchor_ok,
                               cancel_ok, complete, reported_errors, continuation_ok)
from fixture_server import Fixture, message
from native_driver import Owner, Driver
from display_session import DisplaySession, display_environment, wait_for

ROOT = Path(__file__).resolve().parent

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def verify_inventory(portable, record, owner):
    """Check the complete qualified inventory without following escaping symlinks."""
    until = time.monotonic() + 120
    observed, total = [], 0
    pending = [portable]
    while pending:
        owner.check()
        require(time.monotonic() < until, "Inventory deadline exceeded")
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                require(len(observed) < 50000, "Inventory entry cap exceeded")
                path = Path(entry.path)
                relative = path.relative_to(portable).as_posix()
                info = entry.stat(follow_symlinks=False)
                row = {"path": relative, "mode": stat.S_IMODE(info.st_mode)}
                if entry.is_symlink():
                    require(path.resolve().is_relative_to(portable), "Escaping packaged symlink")
                    row.update(type="symlink", target=os.readlink(path))
                elif entry.is_dir(follow_symlinks=False):
                    row.update(type="directory")
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    total += info.st_size
                    require(info.st_size <= 2*1024**3 and total <= 8*1024**3,
                            "Portable inventory byte cap exceeded")
                    row.update(type="file", bytes=info.st_size, sha256=digest(path))
                else:
                    raise GateFailure("Special file in packaged payload")
                observed.append(row)
    observed.sort(key=lambda row: row["path"])
    require(observed == record["entries"], "Portable payload differs from qualifier inventory")
    return True

def case_environment(work, base_env):
    work.mkdir()
    env = dict(base_env)
    for key, sub in (("HOME","home"), ("PROTEUS_HOME","runtime"),
                     ("PROTEUS_CONFIG_HOME","config"), ("XDG_CONFIG_HOME","xdg-config"),
                     ("XDG_DATA_HOME","xdg-data"), ("XDG_STATE_HOME","xdg-state"),
                     ("XDG_CACHE_HOME","xdg-cache"), ("TMPDIR","tmp"),
                     ("PROTEUS_EXTENSIONS_DIR","empty-extensions")):
        path = work / sub
        path.mkdir()
        env[key] = str(path)
    (work / "workspace").mkdir()
    (work / "session").mkdir()
    prefs = Path(env["XDG_CONFIG_HOME"]) / "dev.proteus.native"
    prefs.mkdir()
    (prefs / "preferences.json").write_text(json.dumps({
        "notifications": "off", "sidebar": {"panel": None, "width": 264},
        "view": {"scale": 100, "chat_text": 18, "chat_width": 820, "autoscroll": True},
        "motion": "full", "theme": "dark"}))
    return env

def probe(driver, fixture, owner, result, spec):
    driver.wait_markers(["NATIVEBOOT"], time.monotonic_ns(), "boot")
    driver.type_composer("NATIVESEND")
    driver.send_composer()
    wait_for(owner, lambda: fixture.run_id and fixture.send_ready.is_set(),
             "actual composer /send-async startup sequence")
    first = fixture.delta(0, "BEGINMARK café🙂 OLDTAIL\n\nENDMARK")
    driver.wait_markers(["BEGINMARK", "OLDTAIL", "ENDMARK"], first, "first-delta")
    result["native_window_proven"] = True
    prefix = "BEGINMARK café🙂 "
    corrected = fixture.delta(len(prefix.encode()), "NEWTEXT\n\nENDMARK")
    driver.wait_markers(["BEGINMARK", "NEWTEXT", "ENDMARK"], corrected, "corrected-delta")
    barrier = fixture.tool()
    shot = driver.wait_markers(["BEGINMARK", "ENDMARK", "barrierprobe"], barrier,
                               "barrier-before-copy")
    ordered(shot["receipt"]["words"], ["BEGINMARK", "ENDMARK", "barrierprobe"])
    result["clipboard"] = driver.copy_delta_row(fixture, spec["expected_delta_text"], shot,
                                                "CLIPBOARD-SENTINEL-" + secrets.token_hex(16))
    result["feasibility_gate_passed"] = True
    # Only now may a completion overwrite row text; the delta oracle is already proven.
    same = fixture.delta(len(spec["expected_delta_text"].encode()), " SAMEID")
    same_shot = driver.wait_markers(["BEGINMARK", "ENDMARK", "SAMEID", "barrierprobe"], same, "same-id-barrier")
    ordered(same_shot["receipt"]["words"], ["BEGINMARK", "barrierprobe"])
    continuation_ok(same_shot["receipt"]["words"], "ENDMARK", "SAMEID", "barrierprobe")
    fixture.complete_message(spec["expected_delta_text"] + " SAMEID")
    next_id = str(uuid.UUID(int=101))
    fixture.delta(0, "AFTERBARRIER", next_id)
    final = fixture.complete_message("AFTERBARRIER", next_id)
    final_shot = driver.wait_markers(["BEGINMARK", "barrierprobe", "AFTERBARRIER"], final,
                                    "new-message-after-barrier")
    ordered(final_shot["receipt"]["words"], ["BEGINMARK", "barrierprobe", "AFTERBARRIER"])
    fixture.execution("success", terminal=True)
    for name in ("native_feasibility", "streaming_delta_clipboard", "nontext_barriers"):
        result["scenarios"][name] = {"status": "passed"}

def anchors(driver, fixture, owner, result, spec):
    driver.wait_markers(["INITIALTAIL"], time.monotonic_ns(), "tail-initial")
    found = None
    for _ in range(20):
        driver.wheel(down=False, count=2)
        time.sleep(0.15)
        shot = driver.capture()
        words = shot["receipt"]["words"]
        a = [w for w in words if w["text"] == "ANCHORMARK" and w["confidence"] >= 65]
        b = [w for w in words if w["text"] == "MUTABLEMARK" and w["confidence"] >= 65]
        require(len(a) <= 1 and len(b) <= 1, "Duplicate anchor marker")
        if a and b:
            found = shot
            break
    require(found is not None, "Cannot expose unique anchor and visible mutable row")
    ordered(found["receipt"]["words"], ["ANCHORMARK", "MUTABLEMARK"])
    driver.save(found, "anchor-initial")
    baseline = marker(found["receipt"]["words"], "ANCHORMARK")
    mutable_id = str(uuid.UUID(int=1009))
    def check_anchor(points, shot):
        anchor_ok(baseline, marker(shot["receipt"]["words"], "ANCHORMARK"),
                  spec["anchor_tolerance_px"])
    alpha = fixture.delta(0, "STAGEALPHA", mutable_id)
    driver.wait_markers(["ANCHORMARK", "STAGEALPHA"], alpha, "anchor-alpha",
                        predicate=check_anchor)
    beta = fixture.delta(0, "STAGEBETA\n\nADDEDLINE", mutable_id)
    driver.wait_markers(["ANCHORMARK", "STAGEBETA"], beta, "anchor-beta",
                        predicate=check_anchor)
    # The later visible acknowledgment is delivered after all offscreen tail deltas.
    for index in range(8):
        fixture.delta(0, "OFFSCREEN " + str(index) + "\n\nextra content\n\nextra content",
                      str(uuid.UUID(int=3000+index)))
    fixture.delta(0, "TAILMARK", str(uuid.UUID(int=4000)))
    ack = fixture.delta(0, "TAILACK", mutable_id)
    driver.wait_markers(["ANCHORMARK", "TAILACK"], ack, "anchor-tail-ack",
                        predicate=check_anchor)
    # Resume by real wheel input. Jump-button targeting is outside this initial gate.
    tail = None
    for _ in range(30):
        driver.wheel(down=True, count=4)
        shot = driver.capture()
        matches = [w for w in shot["receipt"]["words"]
                   if w["text"] == "TAILMARK" and w["confidence"] >= 65]
        require(len(matches) <= 1, "Duplicate tail marker")
        if matches:
            tail = shot
            break
    require(tail is not None, "Cannot return to the native list tail")
    driver.wheel(down=True, count=8)
    driver.wait_markers(["TAILMARK"], time.monotonic_ns(), "tail-return")
    # Ungated transport burst: this does not establish the coalescer's runtime batch count.
    burst_id = str(uuid.UUID(int=5000))
    text_length = 0
    for index in range(32):
        fragment = "Burst line " + str(index) + "\n\n"
        fixture.delta(text_length, fragment, burst_id)
        text_length += len(fragment.encode())
    last = fixture.delta(text_length, "BURSTTAIL", burst_id)
    driver.wait_markers(["BURSTTAIL"], last, "ungated-burst-tail")
    result["scenarios"]["scroll_anchor_tail_follow"] = {"status": "passed",
        "anchor_tolerance_px": spec["anchor_tolerance_px"],
        "resume_control": "native wheel-to-end",
        "limits": "Sampled visible geometry with later visible FIFO acknowledgments; no internal anchor identity or every-frame proof."}

def cancellation(driver, fixture, owner, result):
    driver.wait_markers(["CANCELREADY"], time.monotonic_ns(), "cancel-ready")
    receipts = []
    for ordinal, send, draft in (("one","CANCELONE","UNSENTDRAFT"),
                                  ("two","CANCELTWO","SECONDDRAFT")):
        fixture.expected_send = send
        driver.type_composer(send, replace=ordinal == "two")
        previous = fixture.run_id
        driver.send_composer()
        wait_for(owner, lambda: fixture.run_id and fixture.run_id != previous and fixture.send_ready.is_set(),
                 "new native send for cancellation")
        run_id = fixture.run_id
        fixture.delta(0, "CANCELTEXT"+ordinal.upper(), str(uuid.UUID(int=6000+len(receipts))))
        driver.type_composer(draft)
        x,y = driver.stop_control("cancel-"+ordinal+"-target")
        request_count = len([r for r in fixture.requests if r["path"] == "/cancel"])
        clicked = driver.click(x,y,"native Stop")
        def cancel_request():
            calls = [r for r in fixture.requests if r["path"] == "/cancel"]
            return calls[request_count] if len(calls) > request_count else None
        request = wait_for(owner,cancel_request,"native /cancel request")
        cancel_ok(request,fixture.session,run_id)
        pending = fixture.execution("cancel_requested")
        pending_marker = "PENDING"+ordinal.upper()
        fixture.delta(0,pending_marker,str(uuid.UUID(int=6000+len(receipts))))
        def pending_visible(points, shot):
            require(len(driver.red_stop_candidates(shot["image"])) == 1,
                    "Stop disappeared while cancellation remained active")
        driver.wait_markers([draft,pending_marker],pending,"cancel-"+ordinal+"-pending",predicate=pending_visible)
        terminal = fixture.execution("canceled",terminal=True)
        until = time.monotonic()+driver.spec["stage_seconds"]
        final = None
        while time.monotonic() < until:
            shot = driver.capture()
            marker(shot["receipt"]["words"],draft)
            if not driver.red_stop_candidates(shot["image"]):
                final = shot
                break
            time.sleep(0.1)
        require(final is not None,"Stop persisted after terminal active=null")
        driver.save(final,"cancel-"+ordinal+"-terminal")
        receipts.append({"run_id":run_id,"cancel_trace_seq":request["trace_seq"],
                         "click_ns":clicked,"pending_ns":pending,"terminal_ns":terminal,"draft":draft,
                         "pending_claim":"Stop retained while server cancel is pending, after FIFO text acknowledgement; not internal state observation"})
    result["scenarios"]["cancel_repeat"] = {"status":"passed","turns":receipts}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualified-work",type=Path,required=True)
    parser.add_argument("--qualification-evidence",type=Path,required=True)
    parser.add_argument("--work-dir",type=Path,required=True)
    parser.add_argument("--evidence-dir",type=Path,required=True)
    args = parser.parse_args()
    require(os.geteuid() != 0,"Native gate must not run as root")
    work,evidence = args.work_dir.resolve(),args.evidence_dir.resolve()
    require(not work.exists() and not evidence.exists(),"Fresh absent native directories required")
    work.mkdir(parents=True)
    evidence.mkdir(parents=True)
    spec = json.loads((ROOT/"assertions.json").read_text())
    result = {"schema":1,"status":"running","scenarios":{},"captures":[],"cases":{},
              "fixture_errors":[],"evidence_overflow":False,"native_window_proven":False,
              "feasibility_gate_passed":False,"portable_inventory_unchanged":False,
              "rust_log_backend_initialized":False,"renderer_diagnostics_complete":False,
              "limits":spec["limits"],"spec_sha256":digest(ROOT/"assertions.json"),
              "workflow_head":os.environ.get("GITHUB_SHA"),"workflow_run":os.environ.get("GITHUB_RUN_ID")}
    owner = None
    display = None
    def save():
        data = (json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n").encode()
        require(len(data) <= spec["max_result_bytes"],"Native result JSON cap exceeded")
        (evidence/"result.json").write_bytes(data)
    cancellation_signal = []
    def interrupted(number,frame):
        cancellation_signal.append(number)
    for number in (signal.SIGTERM,signal.SIGINT):
        signal.signal(number,interrupted)
    try:
        qualified = json.loads((args.qualification_evidence/"result.json").read_text())
        inventory_file = args.qualification_evidence/"portable-inventory.json"
        inventory = json.loads(inventory_file.read_text())
        require(qualified["status"] == "success" and qualified["phase"] == "complete",
                "Same-job portable qualification has not passed")
        require(qualified["candidate_tree"] == spec["candidate_tree"]
                and qualified["candidate_commit"] == spec["candidate_commit"],
                "Wrong qualified Desktop candidate")
        require(qualified["effective_build_env"].get("npm_config_audit") == "false",
                "Qualifier did not explicitly disable automatic npm audit")
        require(digest(inventory_file) == qualified["portable"]["inventory_sha256"],
                "Qualifier inventory hash mismatch")
        portable = args.qualified_work.resolve()/"desktop/build/Proteus"
        binary = portable/"bin/proteus-native"
        native_hash = qualified["portable"]["copied_binaries"]["proteus-native"]["sha256"]
        native_entries = [row for row in inventory["entries"] if row["path"] == "bin/proteus-native"]
        require(len(native_entries) == 1 and native_entries[0]["sha256"] == native_hash,
                "Native binary identity missing from qualified inventory")
        result.update(qualified_native_sha256=native_hash,native_binary_before=digest(binary),
                      candidate_tree=qualified["candidate_tree"],candidate_commit=qualified["candidate_commit"],
                      qualification_result_sha256=digest(args.qualification_evidence/"result.json"),
                      qualification_inventory_sha256=digest(inventory_file),
                      qualifier_environment_difference=spec["qualifier_environment_difference"])
        require(result["native_binary_before"] == native_hash,"Launched binary differs from qualifier")
        env = display_environment(work)
        owner = Owner(env,time.monotonic()+spec["total_seconds"],spec["max_log_bytes"],
                      canceled=lambda: bool(cancellation_signal))
        verify_inventory(portable,inventory,owner)
        display = DisplaySession(owner)
        display.start()
        result["display_infrastructure"] = display.receipt
        packages = ["xvfb","xauth","openbox","dbus","xdotool","x11-utils","x11-apps","x11-xserver-utils","imagemagick",
                    "tesseract-ocr","tesseract-ocr-eng","tesseract-ocr-rus","python3-pil","xclip",
                    "mesa-vulkan-drivers","libgl1-mesa-dri","vulkan-tools","mesa-utils"]
        result["system_packages"] = owner.run(["dpkg-query","-W","-f",
                    chr(36)+"{binary:Package}\t"+chr(36)+"{Version}\n",*packages]).decode()
        result["tools"] = {"python":owner.run(["/usr/bin/python3","--version"]).decode(),
                           "ocr":owner.run(["tesseract","--version"]).decode(),
                           "vulkaninfo":owner.run(["vulkaninfo","--summary"],timeout=15).decode(),
                           "glxinfo":owner.run(["glxinfo","-B"],timeout=15).decode()}
        result["runtime_environment"] = {key:value for key,value in env.items()
                                         if key not in ("XAUTHORITY","DBUS_SESSION_BUS_ADDRESS")}
        fonts = set(owner.run(["fc-list","--format","%{file}\n"]).decode().splitlines())
        require(len(fonts) <= 1024,"Font inventory cap exceeded")
        result["font_files"] = [{"path":p,"sha256":digest(Path(p))} for p in sorted(fonts)]
        seeds = {"probe":[message("NATIVEBOOT",1)],"cancel":[message("CANCELREADY",2)]}
        history = [message("HISTORY"+chr(65+i)+"MARK",1000+i) for i in range(24)]
        history[8] = message("ANCHORMARK",1008)
        history[9] = message("MUTABLEMARK",1009,streaming=True)
        history.append(message("INITIALTAIL",2000))
        seeds["anchor"] = history
        for case in ("probe","anchor","cancel"):
            case_env = case_environment(work/case,env)
            fixture = Fixture(work/case/"workspace",work/case/"session",secrets.token_hex(24),
                              seeds[case],"NATIVESEND" if case == "probe" else None).start()
            native,driver = None,None
            try:
                native = owner.start("native-"+case,
                     [portable/"proteus-native",work/case/"workspace",
                      "--origin",fixture.origin,"--token",fixture.token],env=case_env)
                driver = Driver(owner,native,evidence,case,spec,fixture)
                result["cases"][case] = {"window":driver.wait_window()}
                wait_for(owner,fixture.connected.is_set,"native SSE subscription")
                if case == "probe":
                    probe(driver,fixture,owner,result,spec)
                elif case == "anchor":
                    anchors(driver,fixture,owner,result,spec)
                else:
                    cancellation(driver,fixture,owner,result)
                driver.alive()
            except BaseException as exc:
                result["cases"].setdefault(case,{})["scenario_error"] = type(exc).__name__+": "+str(exc)
                if driver:
                    driver.save_failure(case)
                raise
            finally:
                try:
                    fixture.close()
                except BaseException as exc:
                    fixture.errors.append("Fixture cleanup: "+type(exc).__name__+": "+str(exc))
                result["fixture_errors"].extend(fixture.errors)
                result["cases"].setdefault(case,{})["protocol"] = list(fixture.trace)
                if driver:
                    result["captures"].extend(driver.captures)
                    result["cases"][case]["inputs"] = driver.inputs
                    driver.close()
                if native:
                    owner.kill(native)
                    native.wait(timeout=3)
                save()
        result["native_binary_after"] = digest(binary)
        result["portable_inventory_unchanged"] = verify_inventory(portable,inventory,owner)
        for capture in result["captures"]:
            require(digest(evidence/capture["file"]) == capture["png_sha256"],"Saved PNG hash mismatch")
        result["receipt_ids"] = [capture["file"].split("-")[0]+":"+capture["stage"]
                                 for capture in result["captures"]]
        result["png_count"],result["png_bytes"] = owner.png_count,owner.png_bytes
        complete(result,spec)
        result["status"] = "passed"
    except BaseException as exc:
        result["status"] = "failed"
        result["error"] = type(exc).__name__+": "+str(exc)
        result["evidence_overflow"] = "cap exceeded" in str(exc).lower()
        raise
    finally:
        if owner:
            if display:
                try:
                    display.close()
                except BaseException as exc:
                    owner.fatal = owner.fatal or "Display cleanup: "+str(exc)
                result["display_infrastructure"] = display.receipt
            owner.close()
            result["utility_commands"] = owner.commands
            result["cleanup_error"] = owner.fatal
            result["cancellation_signals"] = cancellation_signal
            for name,data in owner.logs.items():
                (evidence/(name+".log")).write_bytes(data)
                if name.startswith("native-"):
                    try:
                        reported_errors(data.decode(errors="replace"))
                    except GateFailure as exc:
                        result["status"],result["error"] = "failed",str(exc)
            if owner.fatal:
                result["status"],result["error"] = "failed",owner.fatal
        save()
        require(result["status"] == "passed",result.get("error","Native gate did not pass"))

if __name__ == "__main__":
    main()
