#!/usr/bin/env python3
"""Private four-procedure release resource-smoke outer bridge. UNSEALED.
No execution/publication authority is conferred by this source artifact.
"""
import argparse
import ast
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import types

MIB = 1024*1024
SIDECAR_CAP = MIB
GZIP_CAP = 256*MIB-MIB-65536
STREAM_CAP = 640*1024
STREAM_ENCODED_CAP = 896*1024


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def strict(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate terminal JSON key")
            value[key] = item
        return value
    def invalid(value):
        raise RuntimeError("nonfinite terminal JSON")
    def number(value):
        value = float(value)
        require(math.isfinite(value), "nonfinite terminal number")
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid, parse_float=number)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()+b"\n"


def bounded(path, cap):
    path = Path(path)
    require(path.is_absolute() and str(path.resolve()) == str(path), "canonical bootstrap path required")
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= cap, "bootstrap file type/size")
        raw = bytearray()
        while True:
            piece = os.read(fd, min(65536, cap+1-len(raw)))
            if not piece:
                break
            raw.extend(piece)
            require(len(raw) <= cap, "bootstrap file grew")
        after = os.fstat(fd)
        require(len(raw) == before.st_size and
                (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) ==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),
                "bootstrap file changed")
        return bytes(raw)
    finally:
        os.close(fd)


MODE = "four-resource-smoke"
PLAN_SHA = "04d31854f46bc899e4093c05d8e65fc1a01e746515eeb479ffcf1536a5162d51"
LIMITS = {"wall_seconds":12000, "control_seconds":300, "evidence_bytes":512*MIB,
          "archive_bytes":GZIP_CAP, "terminal_bytes":MIB, "max_files":4096}
PHASES = [("build-baseline",1800),("build-candidate",1800),("build-reference",1800),
          ("procedure-smoke-01",240),("procedure-smoke-02",240),
          ("procedure-smoke-03",240),("procedure-smoke-04",240)]


def source_module(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw,str(path),"exec"),module.__dict__)
    return module


def canonical_template(raw, prefix, replacement):
    lines = raw.splitlines(keepends=True)
    indices = [i for i,line in enumerate(lines) if line.startswith(prefix)]
    require(len(indices) == 1, "unique execution seal required")
    prior = lines[indices[0]]
    lines[indices[0]] = replacement
    return b"".join(lines), prior


def admit(args):
    require(args.mode == MODE and sys.flags.isolated and sys.flags.no_site
            and sys.flags.dont_write_bytecode and not sys.flags.optimize
            and sys.implementation.name == "cpython" and sys.version_info[:2] == (3,10),
            "isolated standard Ubuntu shipping bootstrap")
    root = Path(__file__).resolve().parent.parent
    require(Path(__file__).resolve() == root/"benchmarks/shipping-smoke-launch.py",
            "reviewed launch checkout")
    expected = {"authorization":root/"benchmarks/shipping-smoke-admission/authorization.json",
                "bindings":root/"benchmarks/shipping-smoke-admission/bindings.json",
                "workflow":root/".github/workflows/shipping-release-resource-smoke.yml"}
    require(all(Path(getattr(args,key)).resolve() == value for key,value in expected.items()),
            "exact same-checkout admission locations")
    raw = bounded(args.authorization,128*1024)
    digest = hashlib.sha256(raw).hexdigest()
    require(digest == args.authorization_sha256 and len(digest) == 64, "root authorization digest")
    auth = strict(raw)
    require(auth["status"] == "ROOT_APPROVED_FOUR_RESOURCE_FEASIBILITY_SMOKE"
            and auth["mode"] == MODE and auth["plan_sha256"] == PLAN_SHA
            and auth["outer_limits"] == LIMITS and all(type(x) is int for x in auth["outer_limits"].values())
            and auth["outer_clock_protocol"] == "FIXED_SEVEN_PHASE_ACK_V1",
            "shipping root scope/limits")
    require(hashlib.sha256(bounded(str(Path(__file__).resolve()),128*1024)).hexdigest()
            == auth["reviewed_launcher_sha256"], "launcher mismatch")
    workflow, seal = canonical_template(bounded(args.workflow,128*1024),
        b"  ROOT_AUTHORIZATION_SHA256: ",b'  ROOT_AUTHORIZATION_SHA256: "UNSEALED"\n')
    require(seal == ('  ROOT_AUTHORIZATION_SHA256: "'+digest+'"\n').encode()
            and hashlib.sha256(workflow).hexdigest() == auth["reviewed_workflow_template_sha256"],
            "workflow seal/template mismatch")
    runner = {"repository":os.environ.get("GITHUB_REPOSITORY"),"ref":os.environ.get("GITHUB_REF"),
              "os":os.environ.get("RUNNER_OS"),"arch":os.environ.get("RUNNER_ARCH"),
              "image_os":os.environ.get("ImageOS")}
    require(auth["runner"] == runner and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
            and runner == {"repository":"Qweasd123tg/proteus-modules-dot",
                "ref":"refs/heads/ci/shipping-release-smoke-20261028","os":"Linux","arch":"X64","image_os":"ubuntu22"},
            "declared shipping execution origin")
    require("RUSTFLAGS" not in os.environ and "CARGO_ENCODED_RUSTFLAGS" not in os.environ,
            "ambient Rust flags must be absent, including empty values")
    binding_raw = bounded(args.bindings,128*1024)
    require(hashlib.sha256(binding_raw).hexdigest() == auth["bindings_sha256"],"binding template mismatch")
    binding = strict(binding_raw)
    require(binding["module_paths"]["capture"] ==
            {"root":"wrapper","path":"benchmarks/shipping-stdio-capture.py"},
            "exact outer cleanup source reference")
    capture_path, entry_path = root/"benchmarks/shipping-stdio-capture.py",root/"benchmarks/shipping-smoke-entry.py"
    capture_raw, entry_raw = bounded(str(capture_path),128*1024),bounded(str(entry_path),128*1024)
    entry_template, entry_seal = canonical_template(entry_raw,b"AUTHORIZATION_SHA256 = ",
                                                    b"AUTHORIZATION_SHA256 = None\n")
    require(entry_seal == ('AUTHORIZATION_SHA256 = "'+digest+'"\n').encode()
            and hashlib.sha256(entry_template).hexdigest() == auth["reviewed_entry_template_sha256"]
            and hashlib.sha256(capture_raw).hexdigest() == auth["reviewed_module_hashes"]["capture"],
            "entry/capture exact source admission")
    python = str(Path(sys.executable).resolve())
    require(python.startswith("/usr/bin/python3.") and sys.base_prefix == "/usr",
            "canonical system CPython")
    # Only these two exact root-admitted modules are loaded here. Entry admits the
    # entire remaining code/data/host graph before any of its downloaded imports.
    modules = {"capture":source_module(capture_raw,capture_path,"shipping_outer_capture"),
               "entry":source_module(entry_raw,entry_path,"shipping_outer_entry")}
    host = {"python":python,"python_sha256":hashlib.sha256(bounded(python,128*MIB)).hexdigest(),
            "python_version":sys.version,"sys_path":list(sys.path),
            "entry_postimage_sha256":hashlib.sha256(entry_raw).hexdigest(),
            "entry_template_sha256":auth["reviewed_entry_template_sha256"],
            "capture_sha256":hashlib.sha256(capture_raw).hexdigest(),
            "root":str(root),"github":{key:os.environ.get(key) for key in
                ("GITHUB_REPOSITORY","GITHUB_REF","GITHUB_SHA","GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT",
                 "GITHUB_WORKFLOW_REF","ImageOS","ImageVersion")},
            "image_provenance":{"environment_label":os.environ.get("ImageVersion"),
                "runner_setup_log_label":"EXTERNAL_WORKFLOW_LOG_REQUIRED",
                "equivalence":"IMAGE_LABELS_ARE_OBSERVATIONS_NOT_IMMUTABLE_PROVENANCE"}}
    return auth,binding,modules,host


def worker(args):
    _, _, modules, _ = admit(args)
    deadline = float(args.deadline)
    require(time.monotonic() < deadline <= time.monotonic()+12000, "inherited attempt deadline")
    def observer(event):
        raw = encode({"kind":"clock","value":event})
        require(len(raw) <= 2048, "bounded fixed clock event")
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
        if event["event"] == "begin":
            ack_raw = sys.stdin.buffer.readline(512)
            require(ack_raw.endswith(b"\n") and len(ack_raw) < 512
                    and strict(ack_raw) == {"ack":True,"phase":event["phase"]},
                    "matching outer clock acknowledgement")
    result = modules["entry"].entry(args.authorization,args.bindings,args.work,args.evidence,
                                    outer_observer=observer, outer_started=float(os.environ["SHIPPING_START_MONOTONIC"]))
    result["mode"] = MODE
    raw = encode({"kind":"result","value":result})
    require(len(raw) <= 512*1024, "bounded shipping terminal value")
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0 if result.get("status") == "PENDING_OUTER_TERMINAL_AUTHORITY" else 1


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def clock_event(clock, event, now):
    require(finite(now), "parent monotonic clock")
    require(type(event) is dict and event.get("event") in ("begin","end"),"fixed clock event kind")
    if event["event"] == "begin":
        require(set(event) == {"event","phase","cap_seconds","at"}
                and clock["active"] is None and clock["next"] < len(PHASES), "clock begin fields/order")
        phase,cap = PHASES[clock["next"]]
        require(event["phase"] == phase and finite(event["cap_seconds"])
                and 5 < event["cap_seconds"] <= cap
                and finite(event["at"]) and event["at"] <= now, "declared bounded phase")
        clock["active"] = {"phase":phase,"parent_started":now,"cap_seconds":event["cap_seconds"]}
        return {"ack":True,"phase":phase}
    active = clock["active"]
    require(active is not None and set(event) == {"event","phase","call_started","call_finished",
            "excluded_seconds","cumulative_excluded_seconds"} and event["phase"] == active["phase"],
            "matching clock end")
    begin,end,excluded,cumulative = (event[key] for key in
        ("call_started","call_finished","excluded_seconds","cumulative_excluded_seconds"))
    require(all(finite(x) for x in (begin,end,excluded,cumulative))
            and active["parent_started"] <= begin <= end <= now
            and 0 <= excluded == min(active["cap_seconds"],end-begin)
            and excluded <= now-active["parent_started"] <= active["cap_seconds"]
            and cumulative == clock["excluded"]+excluded, "exact bounded supervised interval")
    clock["excluded"] = cumulative
    clock["receipts"].append(dict(event,parent_started=active["parent_started"],parent_finished=now))
    clock["next"] += 1
    clock["active"] = None
    return None


def control_left(clock, now):
    require(finite(now) and now >= clock["started"], "outer control clock")
    active = clock["active"]
    provisional = 0.0 if active is None else min(active["cap_seconds"],max(0,now-active["parent_started"]))
    return 300-(now-clock["started"]-clock["excluded"]-provisional)


def shipping_candidate(value, package_path, clock, now):
    require(value["mode"] == MODE and value["status"] == "PENDING_OUTER_TERMINAL_AUTHORITY"
            and value["performance_claim"] is None and value["plan_sha256"] == PLAN_SHA
            and value["source_trees"] == {"baseline":"9a122670d8e4360e4cdccc930569f141629baefc",
                                         "candidate":"44021ca3f2cdf91046345460709a254f04299e52"}
            and value["replay_substitution"] == "SOURCE_VERIFIED_REPLAY_SUBSTITUTION"
            and value["replay_fixture_nonstart"] == "NOT_INDEPENDENTLY_OBSERVED",
            "shipping result scope/status")
    require(clock["next"] == 7 and clock["active"] is None
            and finite(value["excluded_noncontrol_seconds"])
            and value["excluded_noncontrol_seconds"] == clock["excluded"]
            and 0 <= clock["excluded"] <= 6360
            and finite(value["entry_started_monotonic"])
            and clock["started"] <= value["entry_started_monotonic"] <= now
            and value["attempt_started_monotonic"] == clock["started"]
            and control_left(clock,now) > 0, "all-wall outer/inner control reconciliation")
    smoke = value["smoke"]
    require(smoke["status"] == "FEASIBILITY_SMOKE_COMPLETE" and smoke["unattempted"] == []
            and smoke["latency_or_effect_statistics"] is None
            and all(type(row["valid"]) is bool for row in smoke["outcomes"])
            and [(row["id"],row["arm"],row["cell"],row["valid"]) for row in smoke["outcomes"]] ==
                [("smoke-01","baseline","small",True),("smoke-02","candidate","small",True),
                 ("smoke-03","baseline","large",True),("smoke-04","candidate","large",True)],
            "exact four resource-only outcomes")
    package = value["evidence_package"]
    require(package["status"] == "PACKAGE_COMPLETE" and package["archive"] == package_path
            and package["compressed_hash_is_complete_archive"] is True
            and package["candidate_feasibility_status"] == "FEASIBILITY_SMOKE_COMPLETE"
            and package["feasibility_status"] == "PENDING_OUTER_TERMINAL_AUTHORITY"
            and package["supervision"]["status"] == "SUPERVISED_STAGE_COMPLETE"
            and package["supervision"]["owned_cleanup_complete"] is True, "package/cleanup not complete")
    require(type(package["compressed_bytes"]) is int and 0 < package["compressed_bytes"] <= GZIP_CAP
            and package["terminal_control_reserved_bytes"] == MIB
            and package["terminal_control_reserved_files"] == 1
            and type(package["uncompressed_bytes_plus_terminal_reserve"]) is int
            and package["uncompressed_bytes_plus_terminal_reserve"] <= 512*MIB
            and type(package["all_retained_file_entries_plus_terminal_reserve"]) is int
            and package["all_retained_file_entries_plus_terminal_reserve"] <= 4096,
            "final evidence ceilings")
    return package


def artifact_hash(path, cap, deadline):
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap, "artifact type/size")
        digest, count = hashlib.sha256(),0
        while True:
            require(time.monotonic() < deadline, "terminal artifact deadline")
            piece = os.read(fd,65536)
            if not piece:
                break
            count += len(piece)
            require(count <= cap, "terminal artifact grew")
            digest.update(piece)
        after = os.fstat(fd)
        require(count == before.st_size and
                (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) ==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),
                "terminal artifact changed")
        return {"bytes":count,"sha256":digest.hexdigest()}
    finally:
        os.close(fd)


def shipping_only(args):
    started = float(os.environ["SHIPPING_START_MONOTONIC"])
    require(finite(started) and 0 <= time.monotonic()-started <= 60, "workflow start clock")
    deadline = started+12000
    clock = {"started":started,"excluded":0.0,"next":0,"active":None,"receipts":[]}
    def alarm(signum, frame):
        raise TimeoutError("original shipping control/global deadline")
    signal.signal(signal.SIGALRM,alarm)
    def arm_timer(reserve=20):
        now = time.monotonic()
        active = clock["active"]
        allowance = 0 if active is None else active["cap_seconds"]
        due = min(deadline-reserve,started+300+clock["excluded"]+allowance-reserve)
        if active is not None:
            due = min(due,active["parent_started"]+active["cap_seconds"])
        require(due > now,"reserved outer control allowance")
        signal.setitimer(signal.ITIMER_REAL,due-now)
    arm_timer()
    auth, bindings, modules, host = admit(args)
    capture = modules["capture"]
    capture.enable_subreaper()
    evidence, terminal_path = Path(args.evidence),Path(args.terminal)
    work = Path(args.work)
    require(all(path.is_absolute() and str(path.resolve()) == str(path) for path in
                (work,evidence,terminal_path)) and terminal_path.name == "terminal-control.jsonl"
            and terminal_path.parent == evidence.parent == work.parent
            and terminal_path.parent.is_dir()
            and not any(os.path.lexists(path) for path in
                (work,evidence,terminal_path,Path(str(evidence)+".tar.gz"),Path(str(evidence)+".tar.gz.partial"))),
            "fresh isolated shipping roots")
    require(shutil.disk_usage(work.parent).free >= 8*1024**3, "initial shipping disk floor")
    out = terminal_path.open("xb",buffering=0)
    written, raw_total, stdout = 0,0,bytearray()
    child,pidfd,selector = None,None,selectors.DefaultSelector()
    reason,value,package = None,None,None
    protocol_buffer = bytearray()
    protocol_result = None
    drain_errors, stream_eof = [], set()
    forced,clean = [],False
    terminal = {"status":"FAILED_CENSORED","mode":MODE,"host":host,
                "authorization_sha256":args.authorization_sha256,
                "source_trees":{"baseline":"9a122670d8e4360e4cdccc930569f141629baefc",
                                "candidate":"44021ca3f2cdf91046345460709a254f04299e52"},
                "replay_substitution":"SOURCE_VERIFIED_REPLAY_SUBSTITUTION",
                "replay_fixture_nonstart":"NOT_INDEPENDENTLY_OBSERVED",
                "module_rpc_lengths":"MODULE_RPC_LENGTH_SOURCE_ENFORCED_NOT_CAPTURED",
                "performance_claim":None,"external_authority":"EXACT_GITHUB_JOB_SUCCESS_STILL_REQUIRED"}
    def frame(value, final=False):
        nonlocal written
        raw = encode(value)
        require(written+len(raw) <= (MIB if final else STREAM_ENCODED_CAP), "terminal sidecar cap")
        require(shutil.disk_usage(work.parent).free >= 2*1024**3, "shipping disk floor")
        require(out.write(raw) == len(raw), "terminal short write")
        written += len(raw)
    def parse_stdout(piece):
        nonlocal protocol_result
        protocol_buffer.extend(piece)
        require(len(protocol_buffer) <= 512*1024,"bounded shipping protocol line")
        while b"\n" in protocol_buffer:
            line,_,tail = protocol_buffer.partition(b"\n")
            protocol_buffer[:] = tail
            packet = strict(line)
            require(set(packet) == {"kind","value"} and protocol_result is None,"fixed terminal protocol")
            if packet["kind"] == "clock":
                require(control_left(clock,time.monotonic()) > 20,"original operational control reserve")
                ack = clock_event(clock,packet["value"],time.monotonic())
                arm_timer()
                if ack is not None:
                    encoded = encode(ack)
                    require(len(encoded) < 512 and os.write(child.stdin.fileno(),encoded) == len(encoded),
                            "complete bounded phase ACK")
            else:
                require(packet["kind"] == "result" and clock["active"] is None,"one terminal result")
                protocol_result = packet["value"]
    try:
        frame({"kind":"started","mode":MODE,"attempt_id":auth["attempt_id"],"limits":LIMITS})
        env = {key:val for key,val in os.environ.items()
               if key in {"PATH","HOME","LANG","LC_ALL","TZ","ImageOS","ImageVersion","RUNNER_OS","RUNNER_ARCH","RUSTUP_HOME","SHIPPING_START_MONOTONIC"}
               or key.startswith("GITHUB_") and key not in {"GITHUB_TOKEN","GITHUB_ENV","GITHUB_PATH"}}
        argv = [host["python"],"-I","-B","-S",str(Path(__file__).resolve()),"--mode",MODE,
                "--worker","--deadline",str(deadline),"--authorization",args.authorization,
                "--authorization-sha256",args.authorization_sha256,"--bindings",args.bindings,
                "--workflow",args.workflow,"--work",args.work,"--evidence",args.evidence,"--terminal",args.terminal]
        child = subprocess.Popen(argv,env=env,stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        # Readers are registered before pidfd acquisition can fail.
        for name,stream in (("stdout",child.stdout),("stderr",child.stderr)):
            os.set_blocking(stream.fileno(),False)
            selector.register(stream,selectors.EVENT_READ,name)
        os.set_blocking(child.stdin.fileno(),False)
        pidfd = os.pidfd_open(child.pid)
        while selector.get_map() or child.poll() is None:
            require(time.monotonic() < deadline-20 and control_left(clock,time.monotonic()) > 20,
                    "outer shipping deadline/control reserve")
            if clock["active"] is not None:
                require(time.monotonic() < clock["active"]["parent_started"]+clock["active"]["cap_seconds"],
                        "original active phase cap")
            require(shutil.disk_usage(work.parent).free >= 2*1024**3, "outer shipping disk floor")
            for key,_ in selector.select(0.05):
                piece = os.read(key.fileobj.fileno(),8192)
                if not piece:
                    stream_eof.add(key.data)
                    selector.unregister(key.fileobj)
                    continue
                kept = piece[:max(0,STREAM_CAP-raw_total)]
                if kept:
                    frame({"kind":key.data,"base64":base64.b64encode(kept).decode(),
                           "complete_chunk":len(kept)==len(piece)})
                    raw_total += len(kept)
                    if key.data == "stdout":
                        stdout.extend(kept)
                        parse_stdout(kept)
                require(len(kept)==len(piece), "outer output cap; failure prefix retained")
        require(child.wait(timeout=max(0,deadline-time.monotonic())) == 0, "shipping child nonzero")
        require(not protocol_buffer and protocol_result is not None,"complete final protocol record")
        value = protocol_result
        package = shipping_candidate(value,str(evidence)+".tar.gz",clock,time.monotonic())
    except BaseException as error:
        reason = type(error).__name__+": "+str(error)[:2048]
    finally:
        # One shutdown origin: at most 10 s for ownership cleanup, then bounded
        # final drain within the same 15 s shutdown envelope and original wall.
        signal.setitimer(signal.ITIMER_REAL,0)
        shutdown_started = time.monotonic()
        active = clock["active"]
        failure_allowance = 0 if active is None else min(active["cap_seconds"],
                                max(0,shutdown_started-active["parent_started"]))
        original_control_deadline = started+300+clock["excluded"]+failure_allowance
        terminal_deadline = min(deadline,original_control_deadline)
        tail_io_deadline = terminal_deadline-5  # Existing final-receipt reserve, never renewed.
        shutdown_deadline = min(tail_io_deadline,shutdown_started+15)
        cleanup_end = min(shutdown_deadline,shutdown_started+10)
        if shutdown_deadline <= shutdown_started:
            reason = reason or "original cleanup/control reserve exhausted"
            # Do not raise here: direct safe kill and nonblocking reap still run.
        else:
            signal.setitimer(signal.ITIMER_REAL,shutdown_deadline-shutdown_started)
        try:
            if child is not None and child.poll() is None:
                if pidfd is not None:
                    signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                else:
                    # Direct child is unreaped; no reusable cached PID identity.
                    os.kill(child.pid,signal.SIGKILL)
                forced.append(child.pid)
                child.wait(timeout=max(0,cleanup_end-time.monotonic()))
        except BaseException as error:
            reason = reason or "direct cleanup: "+str(error)[:2048]
        try:
            if time.monotonic() < cleanup_end:
                forced.extend(capture.reap_adopted(cleanup_end))
                clean = child is None or child.poll() is not None
            else:
                clean = False
                reason = reason or "owned descendant cleanup deadline exhausted; state uncertain"
            require(clean and not forced, "outer forced or uncertain cleanup censors shipping success")
        except BaseException as error:
            reason = reason or "cleanup: "+str(error)[:2048]
        # If the one-shot cleanup alarm fired, do not enter more blocking cleanup
        # work beyond its original deadline. Final stream drain checks that same
        # deadline before each read; exhaustion remains censored.
        # Setup failures (including pidfd_open) cannot bypass pending diagnostics.
        # Preserve only within the ORIGINAL raw/encoded caps. After cap exhaustion
        # drain/discard the remaining suffix, explicitly censored, never success.
        if child is not None:
            for name,stream in (("stdout",child.stdout),("stderr",child.stderr)):
                if name in stream_eof:
                    continue
                try:
                    os.set_blocking(stream.fileno(),False)
                    if stream.fileno() not in selector.get_map():
                        try:
                            selector.register(stream,selectors.EVENT_READ,name)
                        except KeyError:
                            pass
                except BaseException as error:
                    drain_errors.append("reader setup "+name+": "+str(error)[:256])
            retain_more = True
            try:
                while selector.get_map():
                    require(time.monotonic() < shutdown_deadline,"final control drain deadline")
                    for key,_ in selector.select(min(0.05,max(0,shutdown_deadline-time.monotonic()))):
                        piece = os.read(key.fileobj.fileno(),8192)
                        if not piece:
                            stream_eof.add(key.data)
                            selector.unregister(key.fileobj)
                            continue
                        kept = piece[:max(0,STREAM_CAP-raw_total)] if retain_more else b""
                        if kept:
                            try:
                                frame({"kind":key.data,"base64":base64.b64encode(kept).decode(),
                                       "complete_chunk":len(kept)==len(piece),"final_drain":True})
                                raw_total += len(kept)
                                if key.data == "stdout":
                                    stdout.extend(kept)
                            except BaseException as error:
                                retain_more = False
                                drain_errors.append("retained drain prefix: "+str(error)[:256])
                        if len(kept) != len(piece):
                            retain_more = False
                            if "control suffix omitted after cap" not in drain_errors:
                                drain_errors.append("control suffix omitted after cap")
                require(stream_eof == {"stdout","stderr"},"incomplete terminal reader closure")
            except BaseException as error:
                drain_errors.append(type(error).__name__+": "+str(error)[:256])
            if drain_errors:
                reason = reason or "final control drain: "+"; ".join(drain_errors)[:2048]
        signal.setitimer(signal.ITIMER_REAL,0)
        # Each descriptor close is attempted even if another close fails.
        if pidfd is not None:
            try:
                os.close(pidfd)
            except BaseException as error:
                reason = reason or "pidfd close: "+str(error)[:256]
        try:
            selector.close()
        except BaseException as error:
            reason = reason or "selector close: "+str(error)[:256]
        if child is not None:
            for stream in (child.stdout,child.stderr,child.stdin):
                try:
                    stream.close()
                except BaseException as error:
                    reason = reason or "control stream close: "+str(error)[:256]
    try:
        # Shutdown's timer is independent of the remaining terminal I/O timer, but
        # both originate in the same initial control/global allowance.
        if time.monotonic() < tail_io_deadline:
            signal.setitimer(signal.ITIMER_REAL,tail_io_deadline-time.monotonic())
        else:
            reason = reason or "original terminal I/O reserve exhausted"
        try:
            if reason is None:
                observed = artifact_hash(package["archive"],LIMITS["archive_bytes"],tail_io_deadline)
                require(observed == {"bytes":package["compressed_bytes"],"sha256":package["compressed_sha256"]},
                        "shipping archive mismatch")
                files,total = 0,0
                for directory,dirs,names in os.walk(evidence,followlinks=False):
                    require(time.monotonic() < tail_io_deadline, "shipping terminal census deadline")
                    require(all(not (Path(directory)/name).is_symlink() for name in dirs),"indirect retained directory")
                    for name in names:
                        info = (Path(directory)/name).lstat()
                        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(),"retained file type/owner")
                        files += 1
                        total += info.st_size
                        require(files+2 <= LIMITS["max_files"] and total+MIB <= LIMITS["evidence_bytes"],"shipping census cap")
                require(files+1 == package["all_retained_file_entries_including_package"]
                        and total == package["uncompressed_bytes_including_result"],"shipping evidence inventory changed")
                require(artifact_hash(host["python"],128*MIB,tail_io_deadline)["sha256"] == host["python_sha256"],
                        "bootstrap interpreter changed")
                require(hashlib.sha256(bounded(str(Path(host["root"])/"benchmarks/shipping-smoke-entry.py"),128*1024)).hexdigest()
                        == host["entry_postimage_sha256"],"entry postimage changed")
                require(hashlib.sha256(bounded(str(Path(host["root"])/"benchmarks/shipping-stdio-capture.py"),128*1024)).hexdigest()
                        == host["capture_sha256"],"outer capture changed")
                require(clock["active"] is None and control_left(clock,time.monotonic()) > 0,
                        "outer final all-wall controls")
                terminal.update(status="SHIPPING_TERMINAL_COMPLETE_AWAITING_JOB_SUCCESS",
                    archive_path=package["archive"],archive=observed,
                    smoke={"status":value["smoke"]["status"],
                           "outcomes":[{"id":row["id"],"arm":row["arm"],"cell":row["cell"],"valid":row["valid"]}
                                       for row in value["smoke"]["outcomes"]]},
                    postflight_status=value.get("postflight",{}).get("status"),
                    uncompressed_evidence_bytes=total,file_entries_including_terminal=files+2)
        except BaseException as error:
            reason = type(error).__name__+": "+str(error)[:2048]
        if reason is not None and time.monotonic() < tail_io_deadline:
            try:
                present = [Path(str(evidence)+suffix) for suffix in (".tar.gz",".tar.gz.partial")
                           if os.path.lexists(str(evidence)+suffix)]
                aliases = []
                for path in present:
                    info = path.lstat()
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(),"failure artifact type/owner")
                    aliases.append({"path":str(path),"device":info.st_dev,"inode":info.st_ino,"bytes":info.st_size})
                if present:
                    chosen = present[-1]
                    terminal.update(archive_path=str(chosen),
                        archive=artifact_hash(chosen,LIMITS["archive_bytes"],tail_io_deadline),archive_aliases=aliases,
                        archive_scope="CURRENT_FILE_PREFIX_NOT_COMPLETE_ARCHIVE_CLAIM")
            except BaseException as error:
                terminal["artifact_observation_error"] = type(error).__name__+": "+str(error)[:2048]
    except BaseException as error:
        reason = reason or "terminal tail: "+type(error).__name__+": "+str(error)[:2048]
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
    terminal.update(reason=reason,owned_cleanup_complete=clean,forced_owned_pids=forced,
                    child_exit_code=child.returncode if child is not None else None,
                    raw_streams_complete=reason is None and stream_eof == {"stdout","stderr"} and not drain_errors,
                    control_drain_errors=drain_errors,elapsed_seconds=time.monotonic()-started,
                    excluded_noncontrol_seconds=clock["excluded"],phase_receipts=clock["receipts"],
                    control_seconds_remaining=terminal_deadline-time.monotonic(),
                    unreconciled_active_phase=clock["active"],
                    unestablished=["UNINTERRUPTIBLE_KERNEL_D_STATE","BLOCKED_FILESYSTEM_DURABILITY",
                                   "EXACT_IMAGE_SETUP_AND_ENV_LABEL_EQUIVALENCE"])
    if reason is not None or not clean:
        terminal["status"]="FAILED_CENSORED"
    signal.setitimer(signal.ITIMER_REAL,0)
    try:
        require(time.monotonic() < terminal_deadline,"original final receipt deadline")
        signal.setitimer(signal.ITIMER_REAL,terminal_deadline-time.monotonic())
        frame({"kind":"terminal","value":terminal},True)
        out.flush()
        os.fsync(out.fileno())
        require(out.tell() == written <= MIB,"terminal sidecar final size")
        require(time.monotonic() < terminal_deadline,"original deadline after terminal fsync")
    finally:
        out.close()
        signal.setitimer(signal.ITIMER_REAL,0)
    require(time.monotonic() < terminal_deadline,"original deadline after terminal close")
    return 0 if terminal["status"] == "SHIPPING_TERMINAL_COMPLETE_AWAITING_JOB_SUCCESS" else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",required=True,choices=(MODE,))
    parser.add_argument("--worker",action="store_true")
    parser.add_argument("--deadline")
    for key in ("authorization","authorization-sha256","bindings","workflow","work","evidence","terminal"):
        parser.add_argument("--"+key,required=True)
    args=parser.parse_args()
    return worker(args) if args.worker else shipping_only(args)


if __name__ == "__main__":
    raise SystemExit(main())
