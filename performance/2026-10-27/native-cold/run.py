#!/usr/bin/env python3
"""Bounded synthetic benchmark controller; stage 1 by default, --measure is explicit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import stat
import statistics
import sys
import time

from launcher import controls, json_child, launch

BASE = "e9d6bd06df78a5af85d055117a6697187730e30e"
CANDIDATE = "63454d4e8b1e4e6b26d088fce2a17d46f30390ae"
MODULES = "7fceaebc3bed8add9b0e3091110f59deca86ba46"
FIXTURE_CAP = 64 * 1024 * 1024
REPORT_CAP = 4 * 1024 * 1024
CASES = [("inline", 128, 128), ("blob", 32, 512)]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(root):
    result = {}
    total = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(base) / name
            info = path.lstat()
            require(not stat.S_ISLNK(info.st_mode), "symlink in fixture")
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), "special fixture path")
        for name in files:
            path = Path(base) / name
            size = path.stat().st_size
            total += size
            require(total <= FIXTURE_CAP, "physical fixture exceeds 64 MiB including oracle")
            relative = path.relative_to(root).as_posix()
            result[relative] = {"bytes": size, "sha256": digest(path)}
    require(result, "empty fixture")
    return dict(sorted(result.items()))


def file_bytes(entries):
    return sum(row["bytes"] for row in entries.values())


def checked_copy(seed, work, original):
    require(not work.exists(), "refuse reused copy")
    shutil.copytree(seed, work, symlinks=False)
    require(manifest(work) == original, "copy differs from exact seed bytes")


def private_env(root):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C", "LANG": "C", "MALLOC_ARENA_MAX": "2",
        "PYTHONDONTWRITEBYTECODE": "1", "RUST_BACKTRACE": "0",
    }
    for key, directory in [("HOME", "home"), ("XDG_CONFIG_HOME", "xdg"), ("TMPDIR", "tmp")]:
        path = root / directory
        path.mkdir()
        env[key] = str(path)
    return env


def verify(binary, work, mode, env, deadline):
    result = json_child([binary, mode, work], env, deadline)
    require(result["value"] == {"verified": True, "mode": mode}, "verification acknowledgment")
    # Deliberately discard verifier timing/RSS, which includes complete oracle and history.
    return {"mode": mode, "verified": True}


def encoding_summary(seed):
    fixture = json.loads((seed / "fixture.json").read_text())
    relative = Path(fixture["session"])
    require(not relative.is_absolute() and ".." not in relative.parts, "unsafe session path")
    journal = seed / relative / "journal.jsonl"
    lines = journal.read_bytes().splitlines()
    counts = {"inline": 0, "blob": 0}
    for raw in lines[:fixture["snapshots"]]:
        record = json.loads(raw)
        payload = record["payload"]
        kind = payload.get("storage")
        # Confirm actual storage encoding from public stored DTO, not payload size inference.
        require(kind in counts, f"unknown payload storage {kind!r}")
        counts[kind] += 1
    return {"journal_relative": journal.relative_to(seed).as_posix(),
            "historical_encoding": counts, "journal_bytes": journal.stat().st_size}


def arm(binary, work, seed, original, mode, env, deadline, evidence):
    evidence.update(status="STARTED", work_copy=work.name)
    checked_copy(seed, work, original)
    # Hashing/copying intentionally pre-reads pages; this is NOT cold OS cache.
    result = json_child([binary, mode, work], env, deadline)
    value = result.pop("value")
    require(set(value) == {"mode", "elapsed_ns", "pid"} and value["mode"] == mode, "measurement schema")
    require(type(value["pid"]) is int and value["pid"] > 0, "SUT PID")
    result["sut_pid"] = value["pid"]
    require(type(value["elapsed_ns"]) is int and value["elapsed_ns"] > 0, "operation clock")
    result["operation_ns"] = value["elapsed_ns"]
    evidence.update(result)
    result["verification"] = verify(binary, work,
                                    "verify-after" if mode == "recover" else "verify-before",
                                    env, deadline)
    after = manifest(work)
    if mode == "projection":
        require(after == original, "read-only projection changed fixture bytes")
    else:
        fixture = json.loads((work / "fixture.json").read_text())
        journal = (Path(fixture["session"]) / "journal.jsonl").as_posix()
        require(set(after) == set(original), "append created or removed unexpected file")
        lock = (Path(fixture["session"]) / "journal.write.lock").as_posix()
        allowed = {journal, lock}
        require({k:v for k,v in after.items() if k not in allowed} ==
                {k:v for k,v in original.items() if k not in allowed}, "append changed non-journal/lock bytes")
        require((work / lock).read_bytes() == f"pid={value['pid']}\n".encode(), "wrong lease owner bytes")
        before_bytes = (seed / journal).read_bytes()
        changed = (work / journal).read_bytes()
        require(changed.startswith(before_bytes) and len(changed) > len(before_bytes), "journal prefix changed")
        require(changed[len(before_bytes):].count(b"\n") == 1, "append record count")
    # Only disposable copies created here are removed; seed and compact report evidence remain.
    shutil.rmtree(work)
    evidence.update(result, status="PASS")
    return result


def summarize(rows):
    results = []
    for case, _, _ in CASES:
        for mode in ["recover", "projection"]:
            for lane in ["AA", "AB"]:
                selected = [r for r in rows if (r["case"], r["mode"], r["lane"]) == (case, mode, lane)]
                for metric in ["operation_ns", "sut_peak_rss_kib", "process_wall_ns"]:
                    ratios = [r["second_binary"][metric] / r["first_binary"][metric] for r in selected]
                    results.append({"case": case, "mode": mode, "lane": lane, "metric": metric,
                        "pairs":len(ratios), "ratio_B_over_A_or_A2_over_A1_median":statistics.median(ratios),
                        "ratio_min":min(ratios), "ratio_max":max(ratios)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", type=Path, required=True)
    parser.add_argument("--b", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--measure", action="store_true")
    args = parser.parse_args()
    args.a, args.b, args.control = [p.resolve(strict=True) for p in [args.a, args.b, args.control]]
    root = args.output.absolute()
    require(not root.exists(), "output root must be fresh")
    require(shutil.disk_usage(root.parent).free >= 2*1024**3, "hosted free disk below 2 GiB")
    root.mkdir()
    deadline = time.monotonic() + 600
    def expired(signum, frame):
        raise TimeoutError("whole-run wall deadline")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 600)
    env = private_env(root)
    provenance = json.loads(args.provenance.read_text())
    require(provenance["status"] == "PASS", "preparation not complete")
    package = Path(__file__).resolve().parent
    require(all(sha == digest(package/name) for name,sha in provenance["source_files"].items()),
            "package source changed after preparation")
    require(provenance["workflow_sha256"] ==
            digest(package.parents[2]/".github/workflows/native-cold-recovery.yml"), "workflow changed")
    require(provenance["bundle_repository"] == "Qweasd123tg/proteus-modules-dot", "wrong evidence repository")
    if args.measure:
        require(provenance["bundle_head"] == os.environ.get("EXPECTED_HEAD") == os.environ.get("GITHUB_SHA"),
                "measurement bundle differs from exact reviewed head")
    require(provenance["core_a"] == BASE and provenance["core_b"] == CANDIDATE and
            provenance["modules"] == MODULES, "wrong source pins")
    actual_bins = {name: digest(path) for name,path in
                   [("a",args.a), ("b",args.b), ("control",args.control)]}
    require(actual_bins == provenance["binary_sha256"], "built binary identity changed")
    report = {
        "schema":1, "status":"STARTED", "stage":"measure" if args.measure else "qualification",
        "sources":provenance, "environment":{"uname":list(platform.uname()),
            "python":sys.version, "libc":list(platform.libc_ver()),
            "gnu_time_sha256":digest(Path("/usr/bin/time")), "malloc_arena_max":2},
        "limits":{"logical_text_bytes":16*1024**2, "physical_fixture_bytes":FIXTURE_CAP,
            "output_bytes":32*1024**2, "child_seconds":60, "whole_run_seconds":600,
            "report_bytes":REPORT_CAP},
        "rss_controls":[], "fixtures":[], "audits":[], "smoke_arms":[], "pairs":[],
        "scope":"Synthetic obsolete-history stress. Fresh process, byte-identical copied fixtures, "
                "pre-read OS pages. Operation clock excludes open/runtime and 100ms retention; "
                "GNU-time RSS includes full SUT lifetime. No full-agent/UI/model speed claim.",
    }
    try:
        controls(args.control, env, deadline, rows=report["rss_controls"])
        pid_file = root / "hold-pipe.pid"
        try:
            launch([args.control, "hold-pipe", pid_file], env, deadline, timeout=1)
        except TimeoutError:
            require(pid_file.is_file(), "hold-pipe child never started")
            child_pid = int(pid_file.read_text())
            state_file = Path(f"/proc/{child_pid}/stat")
            cleanup_deadline = min(deadline, time.monotonic() + 5)
            while state_file.exists():
                try:
                    state = state_file.read_text().split(") ", 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state in ("Z", "X"):
                    break
                require(time.monotonic() < cleanup_deadline, "owned descendant survived timeout")
                time.sleep(0.01)
            report["descendant_timeout_control"] = "PASS: absent or terminated zombie"
        else:
            raise ValueError("pipe-holding descendant did not exercise timeout")
        for case, count, kib in CASES:
            seed = root / f"seed-{case}"
            seeded = json_child([args.a, "seed", seed, str(count), str(kib)], env, deadline)
            require(seeded["value"] == {"seed_records":count+7, "logical_text_bytes":16*1024**2},
                    "seed logical size or records")
            original = manifest(seed)
            encoding = encoding_summary(seed)
            require(encoding["historical_encoding"][case] == count, "wrong physical encoding")
            verify(args.a, seed, "verify-before", env, deadline)
            verify(args.b, seed, "verify-before", env, deadline)
            require(manifest(seed) == original, "seed verifier changed bytes")
            report["fixtures"].append({"case":case, "logical_text_bytes":count*kib*1024,
                "physical_total_bytes":file_bytes(original), "manifest":original, **encoding})
            for label, binary in [("A",args.a), ("B",args.b)]:
                work = root / f"audit-{case}-{label}"
                checked_copy(seed, work, original)
                audit = verify(binary, work, "audit", env, deadline)
                report["audits"].append(dict(audit, case=case, binary=label))
                shutil.rmtree(work)
            for mode in ["recover", "projection"]:
                for label, binary in [("A",args.a), ("B",args.b)]:
                    smoke = {"case":case, "mode":mode, "binary":label,
                             "scope":"qualification smoke; not comparative performance evidence"}
                    report["smoke_arms"].append(smoke)
                    work = root / f"smoke-{case}-{mode}-{label}"
                    arm(binary, work, seed, original, mode, env, deadline, smoke)
            require(manifest(seed) == original, "seed changed during qualification smoke")
            if args.measure:
                for mode in ["recover", "projection"]:
                    for lane in ["AA", "AB"]:
                        # 10 total paired comparisons: five forward, five reverse.
                        # AA uses the exact same A executable SHA for both logical arms.
                        for pair in range(10):
                            reverse = pair % 2 == 1
                            bins = [("first_binary",args.a),
                                    ("second_binary",args.a if lane == "AA" else args.b)]
                            order = list(reversed(bins)) if reverse else bins
                            row = {"case":case, "mode":mode, "lane":lane, "pair":pair,
                                   "execution_order":[x[0] for x in order]}
                            report["pairs"].append(row)
                            for arm_name, binary in order:
                                work = root / f"work-{case}-{mode}-{lane}-{pair}-{arm_name}"
                                row[arm_name] = {}
                                arm(binary, work, seed, original, mode, env, deadline, row[arm_name])
                            require(manifest(seed) == original, "seed changed during comparison")
        if args.measure:
            report["summary"] = summarize(report["pairs"])
        report["status"] = "PASS"
    except BaseException as error:
        report["status"] = "FAIL"
        report["error"] = {"type":type(error).__name__, "message":str(error)[:4000]}
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        data = json.dumps(report, indent=2, sort_keys=True).encode() + b"\n"
        require(len(data) <= REPORT_CAP, "report exceeds 4 MiB")
        (root / "report.json").write_bytes(data)
        print(json.dumps({"status":report["status"], "report_sha256":hashlib.sha256(data).hexdigest(),
                          "measured_pairs":len(report["pairs"])}), flush=True)


if __name__ == "__main__":
    main()
