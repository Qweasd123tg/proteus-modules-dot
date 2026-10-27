#!/usr/bin/env python3
"""Adversarial oracle tests; NOT compiled app mutation coverage."""
import argparse
import copy
import json
import time
from pathlib import Path
from native_assertions import (GateFailure, require, marker, window_ok, capture_ok, ordered,
                               anchor_ok, clipboard_ok, cancel_ok, reported_errors, complete, continuation_ok)

def run_tests():
    passed = []
    def reject(name, function):
        try:
            function()
        except (GateFailure, ValueError):
            passed.append(name)
        else:
            raise AssertionError("Negative control accepted: " + name)
    def mutate(value, **changes):
        result = copy.deepcopy(value)
        result.update(changes)
        return result
    word = {"text":"ANCHORMARK","confidence":95,"left":100,"top":100,"height":18,"width":90}
    meta = {"pid":123,"viewable":True,"wm_class":"dev.proteus.native","title":"Proteus",
            "width":1280,"height":900,"id":42}
    shot = {"captured_ns":20,"window_id":42,"size":[1280,900],"png_sha256":"a"*64}
    window_ok(meta,123)
    capture_ok(shot,10,meta)
    reject("alive-process-no-mapped-window",lambda:window_ok(mutate(meta,viewable=False),123))
    reject("wrong-client-pid",lambda:window_ok(mutate(meta,pid=456),123))
    reject("wrong-native-class",lambda:window_ok(mutate(meta,wm_class="Fake"),123))
    reject("stale-pre-stage-png",lambda:capture_ok(shot,30,meta))
    reject("wrong-window-png",lambda:capture_ok(mutate(shot,window_id=43),10,meta))
    reject("missing-png-sha",lambda:capture_ok(mutate(shot,png_sha256=""),10,meta))
    reject("missing-visible-marker",lambda:marker([],"ANCHORMARK"))
    reject("duplicate-visible-marker",lambda:marker([word,word],"ANCHORMARK"))
    reject("low-confidence-marker",lambda:marker([mutate(word,confidence=20)],"ANCHORMARK"))
    reject("anchor-vertical-jump",lambda:anchor_ok(word,mutate(word,top=105)))
    reject("anchor-horizontal-jump",lambda:anchor_ok(word,mutate(word,left=105)))
    reject("nontext-order-reversed",lambda:ordered([word,mutate(word,text="TOOL",top=50)],
                                                 ["ANCHORMARK","TOOL"]))
    same_words = [mutate(word,text="ENDMARK",top=100),mutate(word,text="SAMEID",top=100,left=200),
                  mutate(word,text="TOOL",top=200)]
    continuation_ok(same_words,"ENDMARK","SAMEID","TOOL")
    reject("same-id-continuation-after-tool",lambda:continuation_ok(
        [same_words[0],mutate(same_words[1],top=250),same_words[2]],"ENDMARK","SAMEID","TOOL"))
    reject("same-id-new-row-before-tool",lambda:continuation_ok(
        [same_words[0],mutate(same_words[1],top=150),same_words[2]],"ENDMARK","SAMEID","TOOL"))
    expected = "BEGINMARK café🙂 NEWTEXT\n\nENDMARK"
    clip = {"nonce":"distinctnonce","before":"distinctnonce","after":expected,"owner_before":100,
            "owner_after":101,"before_ns":10,"click_ns":20,"after_ns":30,
            "icon_before_sha256":"a"*64,"icon_after_sha256":"b"*64,
            "target_visible":True,"selection":"CLIPBOARD"}
    clipboard_ok(clip,expected,[])
    reject("preloaded-expected-clipboard",lambda:clipboard_ok(mutate(clip,nonce=expected,before=expected),
                                                            expected,[]))
    reject("unchanged-clipboard-owner",lambda:clipboard_ok(mutate(clip,owner_after=100),expected,[]))
    reject("no-native-copy-feedback",lambda:clipboard_ok(mutate(clip,icon_after_sha256="a"*64),expected,[]))
    reject("copy-before-sentinel",lambda:clipboard_ok(mutate(clip,click_ns=5),expected,[]))
    reject("wrong-x11-selection",lambda:clipboard_ok(mutate(clip,selection="PRIMARY"),expected,[]))
    reject("offscreen-copy-target",lambda:clipboard_ok(mutate(clip,target_visible=False),expected,[]))
    reject("completion-heals-before-copy",lambda:clipboard_ok(clip,expected,
                                         [{"at_ns":25,"heals_delta_oracle":True}]))
    reject("snapshot-heals-before-copy",lambda:clipboard_ok(clip,expected,
                                         [{"at_ns":11,"heals_delta_oracle":True}]))
    reject("lost-delta-byte",lambda:clipboard_ok(mutate(clip,after=expected[:-1]),expected,[]))
    request = {"path":"/cancel","session":"session","body":{"target_id":"run-1"}}
    cancel_ok(request,"session","run-1")
    reject("wrong-cancel-session",lambda:cancel_ok(request,"wrong","run-1"))
    reject("wrong-cancel-run",lambda:cancel_ok(request,"session","run-2"))
    for index,text in enumerate(("thread 'main' panicked at", "GPU device lost",
                                 "GPU error during frame (failure 1): bad",
                                 "instance texture write out of bounds",
                                 "wgpu validation error", "wgpu\n  ERROR: bad",
                                 "Failed to create surface","No GPU adapter")):
        reject("reported-renderer-error-"+str(index),lambda text=text:reported_errors(text))
    spec = {"required_scenarios":["one"],"required_receipts":{"one":["one:pixel"]}}
    result = {"scenarios":{"one":{"status":"passed"}},"native_binary_before":"a"*64,
              "native_binary_after":"a"*64,"qualified_native_sha256":"a"*64,
              "portable_inventory_unchanged":True,"evidence_overflow":False,"fixture_errors":[],
              "native_window_proven":True,"feasibility_gate_passed":True,"receipt_ids":["one:pixel"],
              "rust_log_backend_initialized":False,"renderer_diagnostics_complete":False}
    complete(result,spec)
    for name,changes in (
        ("missing-scenario",{"scenarios":{}}),
        ("skipped-scenario",{"scenarios":{"one":{"status":"skipped"}}}),
        ("missing-required-receipt",{"receipt_ids":[]}),
        ("null-binary-identity",{"native_binary_before":None,"native_binary_after":None}),
        ("empty-binary-identity",{"native_binary_before":"","native_binary_after":""}),
        ("wrong-qualified-binary",{"qualified_native_sha256":"b"*64}),
        ("changed-binary",{"native_binary_after":"b"*64}),
        ("changed-portable-inventory",{"portable_inventory_unchanged":False}),
        ("truncated-or-over-budget-evidence",{"evidence_overflow":True}),
        ("fixture-handler-error",{"fixture_errors":["failure"]}),
        ("missing-native-feasibility",{"feasibility_gate_passed":False}),
        ("unsupported-renderer-absence-claim",{"renderer_diagnostics_complete":True})):
        reject(name,lambda changes=changes:complete(mutate(result,**changes),spec))
    return passed

def process_tests():
    # Hosted only, after apt Pillow install. No display, Core, model, or repository code.
    import os
    import sys
    from native_driver import Owner
    results = []
    for label,code,timeout,cap in (
        ("utility-output-overflow","print('x'*10000)",2,100),
        ("utility-timeout","import time;time.sleep(60)",0.2,100),
        ("utility-orphan-pipe","import subprocess,sys,os;subprocess.Popen([sys.executable,'-c',"
         "'import time;time.sleep(60)']);os._exit(0)",0.2,100)):
        owner = Owner({"PATH":os.environ["PATH"]},time.monotonic()+5)
        try:
            try:
                owner.run([sys.executable,"-c",code],timeout=timeout,cap=cap)
            except GateFailure:
                pass
            else:
                raise AssertionError("Bounded utility accepted: "+label)
        finally:
            owner.close()
        require(not owner.processes, "Completed utility handles were retained")
        group = owner.commands[0]["pid"]
        def live_group():
            found = []
            for path in Path("/proc").glob("[0-9]*/stat"):
                try:
                    fields = path.read_text().rsplit(")",1)[1].split()
                    if int(fields[2]) == group and fields[0] != "Z":
                        found.append(path.parent.name)
                except (FileNotFoundError,ProcessLookupError,PermissionError):
                    pass
            return found
        until = time.monotonic()+2
        while live_group() and time.monotonic() < until:
            time.sleep(0.02)
        require(not live_group(),"Live original process-group member survived "+label)
        results.append(label)
    owner = Owner({"PATH":os.environ["PATH"]},time.monotonic()+5)
    try:
        fd_before = len(list(Path("/proc/self/fd").iterdir()))
        for _ in range(20):
            owner.run([sys.executable,"-c","pass"])
        require(len(list(Path("/proc/self/fd").iterdir())) <= fd_before+1,
                "Completed utilities leaked file descriptors")
        require(not owner.processes,"Completed utilities retained Popen handles")
        results.append("utility-fd-and-handle-lifecycle")
    finally:
        owner.close()
    owner = Owner({"PATH":os.environ["PATH"]},time.monotonic()+5,log_cap=100)
    try:
        child = owner.start("synthetic-background",[sys.executable,"-c","print('x'*10000)"])
        child.wait(timeout=2)
        for reader in owner.threads:
            reader.join(timeout=2)
        require(owner.fatal == "Complete background log cap exceeded","Background cap did not fail")
        results.append("background-complete-log-overflow")
    finally:
        owner.close()
    # Inject a real handled signal in the Popen-return/ownership-registration gap.
    import signal
    import native_driver
    canceled = []
    old_handler = signal.signal(signal.SIGTERM,lambda number,frame:canceled.append(number))
    original_popen = native_driver.subprocess.Popen
    def signal_after_popen(*args,**kwargs):
        process = original_popen(*args,**kwargs)
        os.kill(os.getpid(),signal.SIGTERM)
        return process
    owner = Owner({"PATH":os.environ["PATH"]},time.monotonic()+5,canceled=lambda:bool(canceled))
    try:
        native_driver.subprocess.Popen = signal_after_popen
        try:
            owner.start("synthetic-signal",[sys.executable,"-c","import time;time.sleep(60)"])
        except GateFailure:
            pass
        else:
            raise AssertionError("Signal during launch was not observed")
    finally:
        native_driver.subprocess.Popen = original_popen
        owner.close()
        signal.signal(signal.SIGTERM,old_handler)
    require(len(owner.processes) == 1 and owner.processes[0].poll() is not None,
            "Signal during launch left an unowned child")
    results.append("signal-during-launch-owned-cleanup")
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report",type=Path,required=True)
    args = parser.parse_args()
    result = {"schema":1,"status":"failed","scope":"Harness oracle/process controls, not app mutations"}
    try:
        result["oracle_controls"] = run_tests()
        result["process_controls"] = process_tests()
        result["status"] = "passed"
    finally:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+"\n")
    require(result["status"] == "passed","Gate controls failed")

if __name__ == "__main__":
    main()
