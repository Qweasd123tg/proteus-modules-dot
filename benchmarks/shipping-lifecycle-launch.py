#!/usr/bin/env python3
"""Product-free lifecycle-only bootstrap; no shipping entry import or invocation.
Only synthetic wrapper process/pipe and tiny retention/package controls are reachable.
Current root seal is UNSEALED in the accompanying private workflow.
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


LIFECYCLE_KEYS = {"capture", "supervisor", "lifecycle"}
LIMITS = {"wall_seconds": 300, "evidence_bytes": 8*MIB, "archive_bytes": 16*MIB,
          "terminal_bytes": MIB, "max_files": 128}
NOT_RUN = ["shipping_builds", "Core", "Modules", "seed", "readiness", "model_fixture",
           "probe_fixture", "shipping_replay", "L6_product_replay"]


LIFECYCLE_PATHS = {
    "capture": "benchmarks/shipping-stdio-capture.py",
    "supervisor": "benchmarks/shipping-smoke-supervisor.py",
    "lifecycle": "benchmarks/shipping-smoke-lifecycle-controls.py",
}
PYTHON_POLICY = {"implementation": "cpython", "minimum_version": [3,10],
                 "flags": ["-I","-B","-S"],
                 "binding": "OBSERVED_CANONICAL_EXECUTABLE_SHA256_PRE_POST"}


def resolve_module_paths(checkout, declared):
    # A fixed relative map, not an arbitrary path resolver or new runner layer.
    require(type(checkout) is str and Path(checkout).is_absolute(), "absolute checkout required")
    require(type(declared) is dict and declared == LIFECYCLE_PATHS,
            "exact repository-relative lifecycle source paths required")
    return {key: str(Path(checkout)/relative) for key,relative in declared.items()}


def source_module(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def admit(args):
    require(args.mode == "lifecycle-only" and sys.flags.isolated and sys.flags.no_site
            and sys.flags.dont_write_bytecode and not sys.flags.optimize,
            "exact isolated lifecycle-only bootstrap required")
    auth_raw = bounded(args.authorization, 128*1024)
    digest = hashlib.sha256(auth_raw).hexdigest()
    require(len(args.authorization_sha256) == 64 and digest == args.authorization_sha256,
            "root seal mismatch")
    auth = strict(auth_raw)
    require(auth["status"] == "ROOT_APPROVED_PRODUCT_FREE_LIFECYCLE_ONLY"
            and auth["mode"] == "lifecycle-only" and auth["limits"] == LIMITS
            and all(type(value) is int for value in auth["limits"].values()),
            "root approval does not admit this mode or budget")
    require(auth["plan_sha256"] ==
            "04d31854f46bc899e4093c05d8e65fc1a01e746515eeb479ffcf1536a5162d51",
            "lifecycle prerequisite plan differs")
    require(hashlib.sha256(bounded(str(Path(__file__).resolve()),128*1024)).hexdigest() ==
            auth["reviewed_launcher_sha256"], "launcher source differs")
    workflow = bounded(args.workflow,128*1024).splitlines(keepends=True)
    seals = [i for i,line in enumerate(workflow) if line.startswith(b"  ROOT_AUTHORIZATION_SHA256: ")]
    require(len(seals) == 1 and workflow[seals[0]] ==
            ('  ROOT_AUTHORIZATION_SHA256: "'+digest+'"\n').encode(), "workflow seal differs")
    workflow[seals[0]] = b'  ROOT_AUTHORIZATION_SHA256: "UNSEALED"\n'
    require(hashlib.sha256(b"".join(workflow)).hexdigest() ==
            auth["reviewed_workflow_template_sha256"], "workflow template differs")
    # Exact immutable GitHub head is bound externally after publication, not
    # self-referentially embedded in a file included in that future commit.
    declared = auth["runner"]
    expected = {"repository": os.environ.get("GITHUB_REPOSITORY"), "ref": os.environ.get("GITHUB_REF"),
                "os": os.environ.get("RUNNER_OS"), "arch": os.environ.get("RUNNER_ARCH"),
                "image_os": os.environ.get("ImageOS")}
    require(os.environ.get("GITHUB_ACTIONS") == "true" and declared == expected
            and expected["repository"] == "Qweasd123tg/proteus-modules-dot"
            and expected["ref"] == "refs/heads/ci/shipping-smoke-lifecycle-20261028"
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
            and expected["os"] == "Linux" and expected["arch"] == "X64"
            and expected["image_os"] == "ubuntu22", "declared runner context differs")
    raw = bounded(args.bindings,128*1024)
    require(hashlib.sha256(raw).hexdigest() == auth["bindings_sha256"], "lifecycle bindings differ")
    bindings = strict(raw)
    require(set(bindings) == {"schema","mode","python","module_paths","module_hashes"}
            and type(bindings["schema"]) is int and bindings["schema"] == 2 and bindings["mode"] == "lifecycle-only"
            and set(bindings["module_paths"]) == LIFECYCLE_KEYS
            and set(bindings["module_hashes"]) == LIFECYCLE_KEYS
            and bindings["module_hashes"] == auth["reviewed_module_hashes"],
            "unreviewed lifecycle import map")
    checkout = Path(__file__).resolve().parent.parent
    require(Path(__file__).resolve() == checkout/"benchmarks/shipping-lifecycle-launch.py"
            and Path(args.workflow).resolve() == checkout/".github/workflows/shipping-release-lifecycle.yml"
            and Path(args.bindings).resolve() == checkout/"benchmarks/shipping-lifecycle-admission/bindings.json"
            and Path(args.authorization).resolve() == checkout/"benchmarks/shipping-lifecycle-admission/authorization.json",
            "admission files must come from the verified launcher checkout")
    paths = resolve_module_paths(str(checkout), bindings["module_paths"])
    require(all(str(Path(path).resolve()) == path for path in paths.values()),
            "indirect lifecycle source path")
    python = str(Path(sys.executable).resolve())
    require(bindings["python"] == PYTHON_POLICY and sys.implementation.name == "cpython"
            and sys.version_info >= (3,10)
            and all(path and Path(path).is_absolute() for path in sys.path),
            "bootstrap Python policy/path mismatch")
    sources = {}
    for key in sorted(LIFECYCLE_KEYS):
        path = paths[key]
        source = bounded(path,128*1024)
        require(hashlib.sha256(source).hexdigest() == bindings["module_hashes"][key],
                "lifecycle module bytes differ: "+key)
        sources[key] = source
    # Every downloaded module byte is admitted before the first such import.
    modules = {key:source_module(sources[key],paths[key],"lifecycle_"+key)
               for key in sorted(LIFECYCLE_KEYS)}
    host = {"python":python,"version":sys.version,"sys_path":list(sys.path),
            "python_sha256":hashlib.sha256(bounded(python,128*MIB)).hexdigest(),
            "module_hashes":bindings["module_hashes"],"checkout":str(checkout),
            "declared_module_paths":bindings["module_paths"],"resolved_module_paths":paths,
            "python_policy":PYTHON_POLICY,
            "github":{key:os.environ.get(key) for key in
              ("GITHUB_REPOSITORY","GITHUB_REF","GITHUB_SHA","GITHUB_WORKFLOW_REF",
               "GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT","ImageOS","ImageVersion")}}
    return auth, dict(bindings,resolved_module_paths=paths), modules, host


def worker(args):
    _, _, modules, _ = admit(args)
    deadline = float(args.deadline)
    require(time.monotonic() < deadline <= time.monotonic()+LIMITS["wall_seconds"],
            "inherited lifecycle deadline")
    result = modules["lifecycle"].run(modules["capture"],modules["supervisor"],
                                    Path(args.work),Path(args.evidence),deadline-30)
    result["not_run"] = NOT_RUN
    result["mode"] = "lifecycle-only"
    result["performance_claim"] = None
    raw = encode(result)
    require(len(raw) <= 512*1024, "bounded lifecycle return")
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    return 0 if result.get("status") == "LIFECYCLE_CONTROLS_COMPLETE" else 1


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


def lifecycle_candidate(value, archive):
    require(value["mode"] == "lifecycle-only" and value["status"] == "LIFECYCLE_CONTROLS_COMPLETE"
            and value["not_run"] == NOT_RUN and value["performance_claim"] is None,
            "lifecycle result mode/scope differs")
    package = value["evidence_package"]
    require(package["status"] == "PACKAGE_COMPLETE" and package["archive"] == archive
            and package["compressed_hash_is_complete_archive"] is True
            and package["supervision"]["status"] == "SUPERVISED_STAGE_COMPLETE"
            and package["supervision"]["owned_cleanup_complete"] is True,
            "lifecycle package/cleanup incomplete")
    # A lifecycle package is never a four-cell resource feasibility pass.
    require(package.get("candidate_feasibility_status") != "FEASIBILITY_SMOKE_COMPLETE",
            "lifecycle package illegally claims product feasibility")
    require(type(package["compressed_bytes"]) is int and 0 < package["compressed_bytes"] <= LIMITS["archive_bytes"]
            and type(package["uncompressed_bytes_including_result"]) is int
            and 0 <= package["uncompressed_bytes_including_result"] <= LIMITS["evidence_bytes"]
            and type(package["all_retained_file_entries_including_package"]) is int
            and 0 <= package["all_retained_file_entries_including_package"] < LIMITS["max_files"],
            "lifecycle package quotas")
    return package


def lifecycle_only(args):
    started, deadline = time.monotonic(), time.monotonic()+LIMITS["wall_seconds"]
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
            "fresh isolated lifecycle roots")
    require(shutil.disk_usage(work.parent).free >= 8*1024**3, "initial lifecycle disk floor")
    out = terminal_path.open("xb",buffering=0)
    written, raw_total, stdout = 0,0,bytearray()
    child,pidfd,selector = None,None,selectors.DefaultSelector()
    reason,value,package = None,None,None
    drain_errors, stream_eof = [], set()
    forced,clean = [],False
    terminal = {"status":"FAILED_CENSORED","mode":"lifecycle-only","host":host,
                "authorization_sha256":args.authorization_sha256,"not_run":NOT_RUN,
                "performance_claim":None,"external_authority":"EXACT_GITHUB_JOB_SUCCESS_STILL_REQUIRED"}
    def frame(value, final=False):
        nonlocal written
        raw = encode(value)
        require(written+len(raw) <= (MIB if final else STREAM_ENCODED_CAP), "terminal sidecar cap")
        require(shutil.disk_usage(work.parent).free >= 2*1024**3, "lifecycle disk floor")
        require(out.write(raw) == len(raw), "terminal short write")
        written += len(raw)
    try:
        frame({"kind":"started","mode":"lifecycle-only","attempt_id":auth["attempt_id"],"limits":LIMITS})
        env = {key:val for key,val in os.environ.items()
               if key in {"PATH","HOME","LANG","LC_ALL","TZ","ImageOS","ImageVersion","RUNNER_OS","RUNNER_ARCH"}
               or key.startswith("GITHUB_") and key not in {"GITHUB_TOKEN","GITHUB_ENV","GITHUB_PATH"}}
        argv = [host["python"],"-I","-B","-S",str(Path(__file__).resolve()),"--mode","lifecycle-only",
                "--worker","--deadline",str(deadline),"--authorization",args.authorization,
                "--authorization-sha256",args.authorization_sha256,"--bindings",args.bindings,
                "--workflow",args.workflow,"--work",args.work,"--evidence",args.evidence,"--terminal",args.terminal]
        child = subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        # Readers are registered before pidfd acquisition can fail.
        for name,stream in (("stdout",child.stdout),("stderr",child.stderr)):
            os.set_blocking(stream.fileno(),False)
            selector.register(stream,selectors.EVENT_READ,name)
        pidfd = os.pidfd_open(child.pid)
        while selector.get_map() or child.poll() is None:
            require(time.monotonic() < deadline-20, "outer lifecycle deadline")
            require(shutil.disk_usage(work.parent).free >= 2*1024**3, "outer lifecycle disk floor")
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
                require(len(kept)==len(piece), "outer output cap; failure prefix retained")
        require(child.wait(timeout=max(0,deadline-time.monotonic())) == 0, "lifecycle child nonzero")
        require(stdout.endswith(b"\n") and len(stdout.splitlines()) == 1, "one complete terminal JSON required")
        value = strict(bytes(stdout))
        package = lifecycle_candidate(value,str(evidence)+".tar.gz")
    except BaseException as error:
        reason = type(error).__name__+": "+str(error)[:2048]
    finally:
        # One shutdown origin: at most 10 s for ownership cleanup, then bounded
        # final drain within the same 15 s shutdown envelope and original wall.
        shutdown_started = time.monotonic()
        shutdown_deadline = min(deadline,shutdown_started+15)
        cleanup_end = min(shutdown_deadline,shutdown_started+10)
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
            forced.extend(capture.reap_adopted(cleanup_end))
            clean = child is None or child.poll() is not None
            require(clean and not forced, "outer forced or uncertain cleanup censors lifecycle success")
        except BaseException as error:
            reason = reason or "cleanup: "+str(error)[:2048]
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
        if pidfd is not None:
            os.close(pidfd)
        selector.close()
        if child is not None:
            child.stdout.close()
            child.stderr.close()
    try:
        if reason is None:
            observed = artifact_hash(package["archive"],LIMITS["archive_bytes"],deadline)
            require(observed == {"bytes":package["compressed_bytes"],"sha256":package["compressed_sha256"]},
                    "lifecycle archive mismatch")
            files,total = 0,0
            for directory,dirs,names in os.walk(evidence,followlinks=False):
                require(time.monotonic() < deadline, "lifecycle terminal census deadline")
                require(all(not (Path(directory)/name).is_symlink() for name in dirs),"indirect retained directory")
                for name in names:
                    info = (Path(directory)/name).lstat()
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(),"retained file type/owner")
                    files += 1
                    total += info.st_size
                    require(files+2 <= LIMITS["max_files"] and total <= LIMITS["evidence_bytes"],"lifecycle census cap")
            require(files+1 == package["all_retained_file_entries_including_package"]
                    and total == package["uncompressed_bytes_including_result"],"lifecycle evidence inventory changed")
            require(artifact_hash(host["python"],128*MIB,deadline)["sha256"] == host["python_sha256"],
                    "bootstrap interpreter changed")
            for key,path in bindings["resolved_module_paths"].items():
                require(hashlib.sha256(bounded(path,128*1024)).hexdigest() == bindings["module_hashes"][key],
                        "lifecycle source changed")
            terminal.update(status="LIFECYCLE_TERMINAL_COMPLETE_AWAITING_JOB_SUCCESS",
                archive_path=package["archive"],archive=observed,
                controls=value.get("controls"),unestablished=value.get("unestablished"),
                uncompressed_evidence_bytes=total,file_entries_including_terminal=files+2)
    except BaseException as error:
        reason = type(error).__name__+": "+str(error)[:2048]
    if reason is not None and time.monotonic() < deadline:
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
                    archive=artifact_hash(chosen,LIMITS["archive_bytes"],deadline),archive_aliases=aliases,
                    archive_scope="CURRENT_FILE_PREFIX_NOT_COMPLETE_ARCHIVE_CLAIM")
        except BaseException as error:
            terminal["artifact_observation_error"] = type(error).__name__+": "+str(error)[:2048]
    terminal.update(reason=reason,owned_cleanup_complete=clean,forced_owned_pids=forced,
                    child_exit_code=child.returncode if child is not None else None,
                    raw_streams_complete=reason is None and stream_eof == {"stdout","stderr"} and not drain_errors,
                    control_drain_errors=drain_errors,elapsed_seconds=time.monotonic()-started)
    if reason is not None or not clean:
        terminal["status"]="FAILED_CENSORED"
    try:
        require(time.monotonic() < deadline,"terminal write deadline")
        frame({"kind":"terminal","value":terminal},True)
        out.flush()
        os.fsync(out.fileno())
        require(out.tell() == written <= MIB,"terminal sidecar final size")
    finally:
        out.close()
    return 0 if terminal["status"] == "LIFECYCLE_TERMINAL_COMPLETE_AWAITING_JOB_SUCCESS" else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",required=True,choices=("lifecycle-only",))
    parser.add_argument("--worker",action="store_true")
    parser.add_argument("--deadline")
    for key in ("authorization","authorization-sha256","bindings","workflow","work","evidence","terminal"):
        parser.add_argument("--"+key,required=True)
    args=parser.parse_args()
    return worker(args) if args.worker else lifecycle_only(args)


if __name__ == "__main__":
    raise SystemExit(main())
