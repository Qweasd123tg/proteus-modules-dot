"""Check frozen 60 Desktop predecessors and the new #444 source receipt."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root, out = map(Path, sys.argv[1:])
r = root / "r120/startup/roster.json"
pub = root / "r122/published.json"
sha = lambda raw: hashlib.sha256(raw).hexdigest()
raw = r.read_bytes()
assert sha(raw) == "31c1737f03d3fa4dd39d4cdc80363d303c890b98d75283e7a778744ccd06d823"
data = json.loads(raw)
assert data["exact_total"] == 200 and data["already_materialized_count"] == 150
published, = json.loads(pub.read_bytes())
assert published["n"] == 444 and published["head"] == "74bb4ab768b6bfba92ac07a39b9e606ada449c95"
assert published["component"] == "desktop" and published["source_sha256"] == "2a71b35f8657bd48bc1b8d41fd2f8e9f7df4eeaceefe15c61daf7a810d8996fd"
old_group = "already_in_anchor_do_not_reapply"
new_group = "ordered_overlays_apply_only_if_admitted"
data[new_group].append({"pr":published["n"],"component":published["component"],
    "upstream":published["upstream"],"source_path":published["source"],"source_sha256":published["source_sha256"],
    "hard_requirements":[]})
exact = {"LICENSE-GPL","src/ui/"+"workspace/windows.rs","src/ui/extensions/mod.rs","src/ui/tabs/mod.rs"}
checked = []
overlap = []
applied = []
for group in (old_group,new_group):
    for row in data[group]:
        if row["component"] != "desktop":
            continue
        assert row["upstream"] == "b6a7ec2d8d7e486c8aba01291aa8c89774c4cded"
        p = (root/row["source_path"]).resolve(strict=True)
        bytes_ = p.read_bytes()
        assert sha(bytes_) == row["source_sha256"], row["pr"]
        changes = subprocess.check_output(["git","apply","--numstat","-z",str(p)])
        paths = [x.split(b"\t",2)[2].decode() for x in changes.split(b"\0") if x]
        assert all(paths) and len(set(paths)) == len(paths) == bytes_.count(b"\ndiff --git ") + bytes_.startswith(b"diff --git ")
        assert exact.isdisjoint(paths), (row["pr"], paths)
        if any(path.startswith("crates/tabs/") for path in paths):
            overlap.append(row["pr"])
            if group == new_group:
                assert not row["hard_requirements"], row["pr"]
                applied.append((row["pr"], p))
        checked.append(row["pr"])
assert len(set(checked)) == len(checked) == 61 and checked[-1] == 444
assert overlap == [267,318,440,444], overlap
assert [n for n,p in applied] == [440,444]
out.write_text("".join(str(p)+"\n" for n,p in applied))
print("PASS 61 selected Desktop patch hashes through #444; three lifted inputs untouched; anchored #267/#318, projected scoped #440/#444 tabs hunks only")
