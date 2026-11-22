"""Select only Desktop M200 overlays that intersect the exact admitted source slice."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys

root, out = map(Path, sys.argv[1:])
roster = root / "r120/startup/roster.json"
roster_bytes = roster.read_bytes()
assert hashlib.sha256(roster_bytes).hexdigest() == "31c1737f03d3fa4dd39d4cdc80363d303c890b98d75283e7a778744ccd06d823"
data = json.loads(roster_bytes)
assert data["exact_total"] == 200 and data["already_materialized_count"] == 150
slice_exact = {
    "LICENSE-GPL", "src/ui/terminal/mod.rs", "src/ui/terminal/view.rs",
    "src/ui/" + "workspace/spaces.rs", "src/ui/chats/subagent.rs",
}
def selected(path):
    return path.startswith("crates/tabs/") or path in slice_exact
seen, overlaps, overlays, applicable = 0, {}, [], {}
for group in ("already_in_anchor_do_not_reapply", "ordered_overlays_apply_only_if_admitted"):
    for row in data[group]:
        if row["component"] != "desktop":
            continue
        p = (root / row["source_path"]).resolve(strict=True)
        raw = p.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["source_sha256"], row["pr"]
        assert row["upstream"] == "b6a7ec2d8d7e486c8aba01291aa8c89774c4cded"
        numstat = subprocess.check_output(["git", "apply", "--numstat", "-z", str(p)])
        paths = [entry.split(b"\t", 2)[2].decode() for entry in numstat.split(b"\0") if entry]
        assert all(paths) and len(paths) == raw.count(b"\ndiff --git ") + raw.startswith(b"diff --git "), row["pr"]
        assert len(set(paths)) == len(paths), row["pr"]
        hits = sorted(path for path in paths if selected(path))
        if hits:
            overlaps[row["pr"]] = hits
            if group == "ordered_overlays_apply_only_if_admitted":
                assert not row["hard_requirements"], row["pr"]
                overlays.append(p)
                applicable[row["pr"]] = hits
        seen += 1
assert seen == 60
assert list(applicable) == [415, 440, 442] and applicable == {
    415: ["src/ui/terminal/view.rs"],
    440: ["crates/tabs/src/layout.rs"],
    442: ["src/ui/terminal/mod.rs", "src/ui/terminal/view.rs"],
}
assert list(overlaps) == [267, 318, 378, 415, 440, 442], overlaps
out.write_text("".join(str(p) + "\n" for p in overlays))
print("PASS 60 frozen Desktop receipt hashes; anchored #267/#318/#378; scoped overlays #415 view-only, #440 tabs-only, #442 terminal pair; others disjoint")
