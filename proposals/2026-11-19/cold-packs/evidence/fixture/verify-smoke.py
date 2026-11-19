"""Validate the R12 functional run and inspect its fresh offline worker's wire trace."""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


def verify(path):
    log = (path / "core.log").read_text()
    assert "test result: ok. 1 passed;" in log
    match = re.search(r"R12_SMOKE rows=(\d+) after=(\d+) offline_worker=fresh "
                      r"export=byte-identical history_prefix=unchanged retained_revision=verified", log)
    assert match, "missing final /history parity marker"
    rows, total = map(int, match.groups())
    assert rows >= 851 and total == rows + 2
    assert [int(x) for x in re.findall(r"R12_EXPORT rows=(\d+)", log)] == [rows, total, total]
    walks = [(int(n),int(pages)) for n, pages in re.findall(r"R12_SCROLL total=(\d+) pages=(\d+)", log)]
    assert walks == [(n, (n+49)//50) for n in (rows, total)]
    wires = [list(csv.DictReader(p.open())) for p in sorted(path.glob("wire-*.csv"))]
    assert len(wires) == 3, "run a single R9_CASES size and use the unmodified transparent proxy"
    actions = [Counter(row["op"] for row in w) for w in wires]
    assert sum(bool(a["create"] and a["commit"] and not a["read_cache"]) for a in actions) == 1
    assert sum(bool(a["commit"] and a["open_display_snapshot"] and a["write_cache"]) for a in actions) == 1
    offline, = [w for w,a in zip(wires, actions) if a["open"] and not a["create"] and not a["commit"]]
    assert all(row["op"] not in {"acquire_writer", "release_writer", "commit"} for row in offline)
    # Deliberate out-of-range query at the end may itself validate/rebuild; the
    # contract only promises read-only canonical history, not zero disposable writes.
    cache = [r for r in offline if r["op"] == "read_cache" and r["cache_key_class"] == "display-data-<hash>"]
    assert cache
    return {"seed_rows": rows, "settled_rows": total, "complete_walks": walks,
            "offline_writer_operations": 0, "equality": "same-session, full HTTP response bytes",
            "offline_cache_body_reads_including_controls": len(cache),
            "largest_offline_cache_body_response_bytes": max(int(r["response_bytes"]) for r in cache)}


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
