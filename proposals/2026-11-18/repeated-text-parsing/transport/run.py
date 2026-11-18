"""Paired timing and cold-view semantics for a pinned, no-window assistant stream."""
import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calls():
    for n in (1, 4, 16, 64):
        yield "prose", n, 1, "grow"
        if n > 1:
            yield "prose", n, n, "grow"
    yield "prose", 64, 8, "grow"
    yield "prose", 64, 1, "same"
    yield "prose", 64, 1, "invalidation"
    yield "prose", 64, 64, "invalidation"
    yield "late-ref", 64, 1, "grow"
    yield "late-ref", 64, 64, "grow"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("host", "base_packages", "candidate_packages", "fixtures", "out"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--cpu", type=int, default=max(os.sched_getaffinity(0)))
    parser.add_argument("--pairs", type=int, default=6)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    packages = [args.base_packages.resolve(), args.candidate_packages.resolve()]

    def pin():
        os.sched_setaffinity(0, {args.cpu})

    def invoke(case, side, proof):
        name, n, group, mode = case
        cmd = [
            str(args.host.resolve()), str(packages[side]),
            str((args.fixtures / f"{name}.md").resolve()), str(n), str(group), mode,
        ]
        if proof:
            cmd.append("--proof")
        return json.loads(subprocess.check_output(cmd, timeout=90, preexec_fn=pin))

    common = {
        "host_sha256": sha(args.host),
        "renderer_sha256": [sha(p / "markdown-render/bin/markdown-render") for p in packages],
        "cpu": args.cpu, "kernel": platform.release(),
    }
    assert len(set(common["renderer_sha256"])) == 2
    results = dict(common, cases={})
    proofs = dict(common, cases={})
    final_by_fixture = {}
    for case in calls():
        key = "/".join(map(str, case))
        reference = invoke(case, 0, True)
        other = invoke(case, 1, True)
        assert reference == other, (key, "different interim/final tree digest or accounting")
        assert reference["final_sha256"] == final_by_fixture.setdefault(case[0], reference["final_sha256"])
        if case[:3] == ("late-ref", 64, 1):
            stages = reference["proofs"]
            assert "[verify]" in stages[0]["first_html"]
            assert 'href="https://example.org/late-destination"' in stages[-1]["first_html"]
        proofs["cases"][key] = reference
        times = [[], []]
        for pair in range(args.pairs):
            for side in ([0, 1] if pair % 2 == 0 else [1, 0]):
                result = invoke(case, side, False)
                times[side].append(result.pop("elapsed_ns") / 1e6)
                for field, value in result.items():
                    if field != "proofs":
                        assert reference[field] == value, (key, field)
        row = {field: val for field, val in reference.items() if field not in ("elapsed_ns", "proofs")}
        row.update(median_ms=[statistics.median(side) for side in times], run_ms=times)
        results["cases"][key] = row
        print(key, len(row["sent_revisions"]), row["accepted"], row["median_ms"], flush=True)
        for file, data in (("results.json", results), ("proofs.json", proofs)):
            (args.out / file).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
