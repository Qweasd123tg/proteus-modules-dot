#!/usr/bin/env python3
"""Fresh-fixture-only public Core read-cache checks; no upstream scripts/models."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import time

PIN = "1fc3ef223d10322815dd9290a50d045bc95402bb"
RESERVE = 1024**3


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def limits():
    resource.setrlimit(resource.RLIMIT_AS, (768*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_CPU, (60,)*2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8*1024**2,)*2)


def inputs(binary):
    package = Path(__file__).parent
    files = [binary, package / "Cargo.toml", package / "Cargo.lock", Path(__file__),
             *sorted((package / "src").glob("*.rs"))]
    return {str(path): digest(path) for path in files}


class Run:
    def __init__(self, binary, output, tracing):
        self.binary, self.output, self.tracing = binary, output, tracing
        self.env = {"PATH":"/usr/bin:/bin", "LANG":"C.UTF-8"}
        for key, leaf in [("HOME","home"),("XDG_CONFIG_HOME","xdg-config"),
                          ("XDG_CACHE_HOME","xdg-cache"),("XDG_DATA_HOME","xdg-data"),("TMPDIR","tmp")]:
            directory = output / leaf
            directory.mkdir()
            self.env[key] = str(directory)
        self.checks = []

    def execute(self, name, args, trace=False):
        st = os.statvfs(self.output)
        if st.f_bavail*st.f_frsize < RESERVE:
            raise RuntimeError("stop: free disk below1GiBreserve")
        command = [str(self.binary), *map(str,args)]
        if trace:
            command = ["/usr/bin/strace","-f","-qq","-e","trace=openat","-s","4096",
                       "-o",str(self.output / f"{name}.openat.txt"),*command]
        started = time.monotonic()
        timed_out = False
        drain_timed_out = False
        cleanup_error = None
        try:
            process = subprocess.Popen(command, env=self.env, cwd=self.output,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True, preexec_fn=limits)
        except (FileNotFoundError, PermissionError) as error:
            write(self.output / f"{name}.process.json", {"command":command,
                "status":"trace_unavailable" if trace else "spawn_failed","error":repr(error)})
            if trace:
                self.tracing = False
                self.checks.append({"name":name,"status":"trace_unavailable","error":repr(error)})
                return None
            raise
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            # The tracer and its owned fixture child share this newly created group.
            # No configured module can detach: components/providers/plugins are empty.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired as drain_error:
                drain_timed_out = True
                stdout = drain_error.output or b""
                stderr = drain_error.stderr or b""
                if process.stdout: process.stdout.close()
                if process.stderr: process.stderr.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired as wait_error:
                    cleanup_error = repr(wait_error)
        if isinstance(stdout, bytes): stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes): stderr = stderr.decode(errors="replace")
        (self.output / f"{name}.stdout.json").write_text(stdout)
        (self.output / f"{name}.stderr.txt").write_text(stderr)
        write(self.output / f"{name}.process.json", {"command":command,"returncode":process.returncode,
              "wall_seconds":time.monotonic()-started,"traced":trace,"new_process_group":True,
              "timed_out":timed_out,"drain_timed_out":drain_timed_out,"cleanup_error":cleanup_error})
        if timed_out:
            raise RuntimeError(f"{name} exceeded wall bound; owned group killed; partial evidence retained")
        if process.returncode:
            if trace:
                # Any abnormal tracer exit can detach an otherwise live child.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            denied = trace and any(line.startswith("strace:") and "ptrace" in line.lower()
                and ("not permitted" in line.lower() or "permission denied" in line.lower())
                for line in stderr.splitlines())
            if denied:
                self.tracing = False
                self.checks.append({"name":name,"status":"trace_unavailable","reason":"ptrace denied; no tracing retry"})
                return None
            raise RuntimeError(f"{name} failed rc={process.returncode}; see retained stderr")
        value = json.loads(stdout)
        assert value["core_pin"] == PIN
        if trace:
            trace_text = (self.output / f"{name}.openat.txt").read_text()
            value["openat_observations"] = {
                "view_cache_open_calls":sum('/.read-view.json"' in line for line in trace_text.splitlines()),
                "canonical_journal_open_calls":sum('/journal.jsonl"' in line for line in trace_text.splitlines()),
            }
        self.checks.append({"name":name,"value":value})
        return value

    def prepare(self, name, count):
        root = self.output / f"dataset-{name}"
        result = self.execute(f"{name}-prepare",["prepare",root,count])
        session = Path(result["session_dir"]).resolve(strict=True)
        assert session.is_relative_to(root.resolve())
        original = root / "original-evidence"
        original.mkdir()
        hashes = {}
        for filename in ["journal.jsonl","session.json",".read-view.json",".read-summary.json"]:
            source = session / filename
            data = source.read_bytes()
            (original / filename).write_bytes(data)
            hashes[filename] = hashlib.sha256(data).hexdigest()
        write(root / "before-mutation-hashes.json",hashes)
        return root, session, original

    def functional(self):
        count = 64
        root, session, _ = self.prepare("positive",count)
        self.execute("positive-read",["read",session,count])
        self.execute("positive-native-reopen",["reopen",root,session,count])
        if self.tracing:
            view = self.execute("positive-snapshot-trace",["only",session,"snapshot",count],True)
            if view is not None:
                observed = view["openat_observations"]
                assert observed["view_cache_open_calls"] > 0 and observed["canonical_journal_open_calls"] == 0
            if self.tracing:
                strict = self.execute("positive-projection-trace",["only",session,"projection",count],True)
                if strict is not None:
                    assert strict["openat_observations"]["canonical_journal_open_calls"] > 0
        root, session, _ = self.prepare("rollback",count)
        self.execute("rollback-control",["rollback",session,count])
        self.execute("rollback-fresh-reader",["read",session,count])
        root, session, _ = self.prepare("append",count)
        self.execute("append-invalidation",["append",root,session,count])
        self.execute("append-fresh-reader",["read",session,count+1])
        for damage in ["malformed","checksum","schema","journal-schema"]:
            root, session, original = self.prepare(f"cache-{damage}",count)
            cache = session / ".read-view.json"
            if damage == "malformed":
                cache.write_bytes(b"{broken")
            else:
                envelope = json.loads(cache.read_bytes())
                if damage == "checksum": envelope["checksum"] = "0"*64
                elif damage == "schema": envelope["schema_version"] = 999
                else: envelope["journal_schema_version"] = 999
                cache.write_text(json.dumps(envelope))
            (root / "damaged-cache.json").write_bytes(cache.read_bytes())
            assert digest(session / "journal.jsonl") == digest(original / "journal.jsonl")
            self.execute(f"cache-{damage}-fallback",["read",session,count])
            assert digest(session / "journal.jsonl") == digest(original / "journal.jsonl")
            if self.tracing and damage == "schema":
                control = self.execute("schema-fallback-trace",["only",session,"snapshot",count],True)
                if control is not None:
                    assert control["openat_observations"]["view_cache_open_calls"] > 0
                    assert control["openat_observations"]["canonical_journal_open_calls"] > 0
        for damage in ["malformed","schema"]:
            root, session, original = self.prepare(f"canonical-{damage}",count)
            self.execute(f"canonical-{damage}-before-damage-positive",["positive-source",root,session,count])
            journal = session / "journal.jsonl"
            if damage == "malformed":
                journal.write_bytes(journal.read_bytes()+b"{broken}\n")
            else:
                lines=journal.read_bytes().splitlines()
                record=json.loads(lines[0]); record["schema_version"]=0
                lines[0]=json.dumps(record).encode()
                journal.write_bytes(b"\n".join(lines)+b"\n")
            (root / "damaged-journal.jsonl").write_bytes(journal.read_bytes())
            # Canonical damage is isolated; native caches themselves remain byte-identical.
            assert digest(session / ".read-view.json") == digest(original / ".read-view.json")
            self.execute(f"canonical-{damage}-strict-vs-display",["invalid-source",root,session,count,damage])

    def measurements(self):
        for count in [64,256]:
            for repeat in range(1,4):
                name=f"measure-{count}-r{repeat}"
                root,session,_=self.prepare(name,count)
                self.execute(name,["read",session,count])
                self.execute(name+"-native-reopen",["reopen",root,session,count])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--binary",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--stage",required=True,choices=["functional","measurements"])
    parser.add_argument("--trace",action="store_true",help="trace only own diagnostic children; never combine trace timings with measurements")
    args=parser.parse_args()
    binary=args.binary.resolve(strict=True)
    args.output.mkdir(parents=False,exist_ok=False)
    output=args.output.resolve()
    before=inputs(binary)
    tracer = None
    tracing = args.trace
    if args.trace:
        try:
            version = subprocess.run(["/usr/bin/strace", "--version"], capture_output=True, text=True, timeout=10)
            tracer = {"version_returncode":version.returncode,"version":version.stdout,"binary_sha256":digest(Path("/usr/bin/strace"))}
            tracing = version.returncode == 0
        except (FileNotFoundError, PermissionError) as error:
            tracer = {"status":"unavailable","error":repr(error)}
            tracing = False
    run=Run(binary,output,tracing)
    write(output / "environment.json",{"core_pin":PIN,"platform":platform.platform(),
          "started_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"stage":args.stage,
          "isolated_child_environment":run.env,"source_and_binary_hashes_before":before,
          "limits":{"child_wall_seconds":120,"child_cpu_seconds":60,"child_address_space_bytes":768*1024**2,"disk_reserve_bytes":RESERVE,"max_child_file_bytes":8*1024**2},
          "allocator_limits":"process-wide requested counters; separate relaxed loads are not one coherent atomic live-memory snapshot; no RSS or precise alloc-minus-free inference",
          "traces_requested":args.trace,"tracer":tracer})
    try:
        if args.stage=="functional":run.functional()
        else:run.measurements()
        after=inputs(binary)
        assert before==after,"binary/source changed during run"
        write(output / "result.json",{"status":"passed","checks":run.checks,"source_and_binary_unchanged":True,
              "source_and_binary_hashes_after":after,"tracing_available_at_end":run.tracing,"not_claimed":["production latency","release benchmark","p95","RSS","cache hit from semantic equivalence alone","execution resume authority test"]})
    except BaseException as error:
        write(output / "result.json",{"status":"failed","error":repr(error),"completed_checks":run.checks})
        raise
    print(output / "result.json")

if __name__=="__main__": main()
