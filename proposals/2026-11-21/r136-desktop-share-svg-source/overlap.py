"""Verify all selected Desktop predecessors through #451 and exact scoped overlap."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root, out, plan = map(Path, sys.argv[1:])
sha=lambda b: hashlib.sha256(b).hexdigest()
roster=(root/"r136/startup/roster.json").read_bytes()
assert sha(roster)=="c8bbead5f22c6e4253fdd8eeb72298dec65103ef8a0cd87cd769166e60467396"
r=json.loads(roster)
assert r["exact_total"]==209 and r["already_materialized_count"]==150
receipt=(root/"r134/published.json").read_bytes()
assert sha(receipt)=="f15e7c405aa62f272202f0ad0de60e4dc20f421d03e9352da7264d4a5658fe40"
last=json.loads(receipt)
assert (last["number"],last["head"],last["source_sha256"])==(451,
    "2cf618606d183f03fd26e95129b6961e46ff6949",
    "87700fd236ca0a04086ae3f8a88e29c54166157c750feaf285cbd6abb7a9634e")
base="b6a7ec2d8d7e486c8aba01291aa8c89774c4cded"
old,new="already_in_anchor_do_not_reapply","ordered_overlays_apply_only_if_admitted"
scope=plan.read_text().splitlines()
def matches(file):
    return any(file==f or file.startswith(f+"/") for f in scope)
immutable={"src/declarative/svg.rs","src/ui/extensions/declarative/images.rs",
           "src/ui/extensions/declarative/images/raster.rs","src/ui/extensions/declarative/images/cache.rs",
           "src/ui/extensions/declarative/images/budget.rs","src/ui/render_image.rs"}
checked,applied=[],[]
for group in (old,new):
    for row in r[group]:
        if row["component"]!="desktop": continue
        p=(root/row["source_path"]).resolve(strict=True)
        raw=p.read_bytes()
        assert row["upstream"]==base and sha(raw)==row["source_sha256"],row["pr"]
        changes=subprocess.check_output(["git","apply","--numstat","-z",str(p)])
        files=[x.split(b"\t",2)[2].decode() for x in changes.split(b"\0") if x]
        assert len(set(files))==len(files)==raw.count(b"\ndiff --git ")+raw.startswith(b"diff --git ")
        assert not immutable.intersection(files)
        hit=sorted(f for f in files if matches(f))
        if hit and group==new:
            assert not row["hard_requirements"]
            applied.append((row["pr"],p,hit))
        if row["pr"]==451:
            assert row["source_sha256"]==last["source_sha256"] and hit==[]
        checked.append(row["pr"])
assert len(set(checked))==len(checked)==64 and checked[-1]==451
out.write_text("".join(str(p)+"\n" for _,p,_ in applied))
print("PASS 64 selected Desktop receipt hashes through #451; scoped overlays:",
      ",".join(str(n) for n,_,_ in applied))
for n,_,hit in applied:
    print(n, " ".join(hit))
