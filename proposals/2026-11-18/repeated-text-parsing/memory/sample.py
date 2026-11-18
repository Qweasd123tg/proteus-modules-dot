"""Linux PSS sampled in sweeps over the same live host+renderer; no build changes."""
import argparse
import hashlib
import json
import os
import select
import statistics
import subprocess
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pss(pid):
    for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines():
        if line.startswith("Pss:"):
            return int(line.split()[1])
    raise ProcessLookupError(pid)


def run(host, packages, path, cpu, group):
    start = time.monotonic_ns()
    command = [host, packages, path, "64", str(group), "grow"]
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, preexec_fn=lambda: os.sched_setaffinity(0, {cpu})
    ) as process:
        pid, child = process.pid, None
        sweeps = []
        executable = (packages / "markdown-render/bin/markdown-render").resolve()
        while not select.select([process.stdout], [], [], .001)[0]:
            try:
                if child is None:
                    children = []
                    for status in Path("/proc").glob("[0-9]*/status"):
                        try:
                            info = status.read_text()
                        except (FileNotFoundError, ProcessLookupError):
                            continue
                        if any(l.startswith("PPid:") and int(l.split()[1]) == pid for l in info.splitlines()):
                            children.append(status.parent.name)
                    if not children:
                        continue
                    assert len(children) == 1
                    found = int(children[0])
                    if Path(f"/proc/{found}/exe").resolve() != executable:
                        continue
                    child = found
                a = time.monotonic_ns()
                host_pss, child_pss = pss(pid), pss(child)
                b = time.monotonic_ns()
                sweeps.append((host_pss, child_pss, (b-a)/1000, (b-start)/1e6))
            except (FileNotFoundError, ProcessLookupError):
                continue
        result = json.load(process.stdout)
        assert process.wait(timeout=5) == 0
    assert len(sweeps) >= 4, len(sweeps)
    peak = max(sweeps, key=lambda s: s[0]+s[1])
    expected = list(range(64)) if group == 1 else [0, 63]
    assert result["sent_revisions"] == expected
    assert result["accepted"] == (64 if group == 1 else 1)
    return {
        "samples": len(sweeps), "sum_at_peak_kib": sum(peak[:2]),
        "host_renderer_kib_at_peak": peak[:2], "t_peak_ms_since_launch": peak[3],
        "first_pair_kib": sweeps[0][:2], "last_pair_kib": sweeps[-1][:2],
        "max_sweep_us": max(s[2] for s in sweeps), "final_tree_sha256": result["final_sha256"],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("host", "before", "after", "fixtures", "timing_reference"):
        p.add_argument(key, type=Path)
    p.add_argument("--cpu", type=int, default=max(os.sched_getaffinity(0)))
    args = p.parse_args()
    host = args.host.resolve()
    sides = [args.before.resolve(), args.after.resolve()]
    reference = json.loads(args.timing_reference.read_text())
    hashes = [sha(s/"markdown-render/bin/markdown-render") for s in sides]
    assert reference["host_sha256"] == sha(host) and reference["renderer_sha256"] == hashes
    out = {"host_sha256": sha(host), "renderer_sha256": hashes, "cpu": args.cpu, "cases": {}}
    for name, group in (("prose", 1), ("late-ref", 1), ("late-ref", 64)):
        groups = [[], []]
        expected = reference["cases"][f"{name}/64/{group}/grow"]["final_sha256"]
        for pair in range(4):
            for side in ((0, 1) if pair % 2 == 0 else (1, 0)):
                result = run(host, sides[side], args.fixtures/(name+".md"), args.cpu, group)
                assert result["final_tree_sha256"] == expected
                groups[side].append(result)
        peaks = [statistics.median(r["sum_at_peak_kib"] for r in group) for group in groups]
        out["cases"][f"{name}/64/{group}"] = {"median_sampled_peak_kib": peaks, "runs": groups}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
