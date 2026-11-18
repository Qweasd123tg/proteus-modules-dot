"""AB/BA warm transport latency and separate two-process Linux PSS sweeps."""

import argparse
import hashlib
import json
import os
import platform
import select
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RENDERER = Path("markdown-render/bin/markdown-render")
SHORT = "Покажи изменения в отчёте и объясни, почему цифры отличаются."
PROSE = "Обычный вопрос про файл: x < y && y > z. \n**это буквальный текст**\n"
# name, text before per-request suffix, timed requests, sampled requests
CASES = [
    ("short", SHORT, 96, 128),
    ("short_url", SHORT + " https://example.org/q?a=1&b=2", 96, 128),
    ("plain_53k", PROSE * 512, 12, 32),
    ("url_53k", PROSE * 512 + " https://example.org/x", 12, 32),
    ("plain_860k", PROSE * 8192, 2, 4),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pss(pid):
    rows = Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines()
    return int(next(row for row in rows if row.startswith("Pss:")).split()[1])


def renderer_pid(pid, packages):
    children = []
    for status in Path("/proc").glob("[0-9]*/status"):
        try:
            info = status.read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if any(row.startswith("PPid:") and int(row.split()[1]) == pid for row in info.splitlines()):
            children.append(int(status.parent.name))
    assert len(children) == 1, children
    child = children[0]
    assert Path(f"/proc/{child}/exe").resolve() == (Path(packages) / RENDERER).resolve()
    return child


def measure(command, memory, cpu):
    def pin():
        os.sched_setaffinity(0, {cpu})

    if not memory:
        return json.loads(subprocess.check_output(command, preexec_fn=pin, timeout=60))

    with subprocess.Popen(
        command + ["--memory"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        preexec_fn=pin,
    ) as proc:
        def ack():
            proc.stdin.write("go\n")
            proc.stdin.flush()

        assert proc.stdout.readline() == "READY\n"
        child = renderer_pid(proc.pid, command[1])
        samples = []

        def snapshot():
            start = time.monotonic_ns()
            host_kib, child_kib = pss(proc.pid), pss(child)
            end = time.monotonic_ns()
            samples.append((host_kib, child_kib, round((end - start) / 1e3)))

        snapshot()
        ack()
        while not select.select([proc.stdout], [], [], 0.001)[0]:
            snapshot()
        assert proc.stdout.readline() == "DONE\n"
        snapshot()
        ack()
        result = json.loads(proc.stdout.readline())
        assert proc.wait(timeout=10) == 0

        peak = max(samples, key=lambda sample: sum(sample[:2]))
        return {
            "samples": len(samples),
            "at_largest_sum_host_renderer_kib": peak[:2],
            "sampled_sum_pss_peak_kib": sum(peak[:2]),
            "warm_idle_kib": samples[0][:2],
            "final_kib": samples[-1][:2],
            "max_sweep_us": max(sample[2] for sample in samples),
            "last_html_sha256": result["html_sha256"][-1],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("host", "base_packages", "patched_packages"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--cpu", type=int, default=max(os.sched_getaffinity(0)))
    args = parser.parse_args()
    host = str(args.host.resolve())
    sides = [args.base_packages.resolve(), args.patched_packages.resolve()]
    out = {
        "kernel": platform.release(),
        "cpu": args.cpu,
        "host_sha256": sha(args.host),
        "renderer_sha256": [sha(packages / RENDERER) for packages in sides],
        "cases": {},
    }
    assert len(set(out["renderer_sha256"])) == 2
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fixture.txt"
        for name, source, count, memory_count in CASES:
            path.write_text(source)
            measures = {}
            for key, memory, runs, n in (
                ("time", False, 8, count),
                ("memory", True, 4, memory_count),
            ):
                pairs = [[], []]
                hashes = None
                for r in range(runs):
                    for side in ([0, 1] if r % 2 == 0 else [1, 0]):
                        command = [host, str(sides[side]), str(path), str(n)]
                        value = measure(command, memory, args.cpu)
                        digest = value["last_html_sha256"] if memory else value["html_sha256"]
                        if hashes is None:
                            hashes = digest
                        assert hashes == digest
                        pairs[side].append(value if memory else statistics.median(value["ns"]))
                measures[key] = pairs
                if memory:
                    measures["median_sampled_pair_pss_kib"] = [
                        statistics.median(v["sampled_sum_pss_peak_kib"] for v in pair)
                        for pair in pairs
                    ]
                else:
                    measures["median_ms"] = [statistics.median(pair) / 1e6 for pair in pairs]
            first = (source + " 0").encode()
            measures["first_source_bytes"] = len(first)
            measures["first_source_sha256"] = hashlib.sha256(first).hexdigest()
            out["cases"][name] = measures
            print(
                name, measures["median_ms"], measures["median_sampled_pair_pss_kib"],
                file=sys.stderr, flush=True,
            )
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
