"""Compare two Core/JSONL combinations against exactly one cold checkpoint."""
import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import statistics
import tempfile

import probe as p


def absolute(s):
    return pathlib.Path(s).resolve(strict=True)


def swap_link(link, target):
    temp = link.with_suffix(".swap")
    temp.symlink_to(target)
    temp.replace(link)


async def run(a):
    assert a.reps >= 4 and a.reps % 4 == 0, "each four-round block uses balanced ABBA"
    binaries = {"stock": (a.stock_cli, a.stock_worker), "patch": (a.patch_cli, a.patch_worker)}
    print(json.dumps({"record": "manifest", "kind": "paired across binaries and display-head conditions",
                      "binaries": {name: [p.fhash(art) for art in files] for name, files in binaries.items()},
                      "reference": p.fhash(p.REF), "rows": a.rows, "width": a.width}), flush=True)
    with tempfile.TemporaryDirectory(prefix="proteus-paired-") as tmp:
        base = pathlib.Path(tmp)
        link = base / "worker"
        swap_link(link, a.stock_worker)
        p.WORKER = link
        p.CLI = a.stock_cli
        cli = p.config(base)
        seed = await p.seed(cli, a.rows, a.width)
        cp = seed["checkpoint"]
        d = pathlib.Path(cp["session"]["session_dir"])
        assert d.resolve() == d and d.is_relative_to(base)
        journal = d / "journal.jsonl"
        stats = p.journal_stats(journal)
        head = d / p.HEAD
        head.unlink(missing_ok=True)
        _, first = await p.attach(cli, cp)
        roots = {seed["root_thread_id"], first}
        hd = head.read_bytes()
        assert json.loads(hd)["source"]["revision"] == cp["revision"]

        def witness():
            st = journal.stat()
            return p.fhash(journal), st.st_size, st.st_dev, st.st_ino, st.st_mtime_ns, st.st_ctime_ns

        origin = witness()
        print(json.dumps({"record": "fixture", "journal_sha256": origin[0], "journal_bytes": origin[1],
                          "head_sha256": hashlib.sha256(hd).hexdigest(), **stats}), flush=True)

        for i in range(a.reps):
            arms = ("stock", "patch") if i % 4 in {0, 3} else ("patch", "stock")
            conditions = ("present", "missing") if i % 2 == 0 else ("missing", "present")
            for condition in conditions:
                for arm in arms:
                    binary, worker = binaries[arm]
                    swap_link(link, worker)
                    assert link.resolve() == worker
                    if condition == "present":
                        temp = base / "head-restore"
                        temp.write_bytes(hd)
                        temp.replace(head)
                        assert head.read_bytes() == hd
                    else:
                        head.unlink(missing_ok=True)
                    assert witness() == origin
                    data, root = await p.attach([str(binary), *cli[1:]], cp)
                    assert root not in roots
                    assert witness() == origin
                    roots.add(root)
                    print(json.dumps({"record": "sample", "round": i + 1,
                                      "arm": arm, "head": condition, **data}), flush=True)


def summarize(path):
    data = [json.loads(s) for s in path.read_text().splitlines()]
    values = {}
    for row in data:
        if row["record"] == "sample":
            key = (row["arm"], row["head"], row["round"])
            assert key not in values
            values[key] = row["ready"]["arrival_ms"]
    assert len(values) == (len(data) - 2) and len(values) >= 16
    for head in ("present", "missing"):
        paired = [(values["stock", head, i], values["patch", head, i])
                  for i in sorted({i for _, _, i in values})]
        print(head, "n=", len(paired))
        for label, series in (
                ("stock", [a for a, _ in paired]),
                ("patch", [b for _, b in paired]),
                ("paired delta (patch minus stock)", [b-a for a, b in paired])):
            print(f"  {label}: {statistics.median(series):.3f} ms [{min(series):.3f}, {max(series):.3f}]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-cli", type=absolute)
    ap.add_argument("--stock-worker", type=absolute)
    ap.add_argument("--patch-cli", type=absolute)
    ap.add_argument("--patch-worker", type=absolute)
    ap.add_argument("--rows", default=5000, type=int)
    ap.add_argument("--width", default=175, type=int)
    ap.add_argument("--reps", default=8, type=int)
    ap.add_argument("--summarize", type=absolute)
    args = ap.parse_args()
    if args.summarize:
        summarize(args.summarize)
    else:
        if not all([args.stock_cli, args.stock_worker, args.patch_cli, args.patch_worker]):
            ap.error("set the stock and patched Core and worker binaries")
        asyncio.run(run(args))
