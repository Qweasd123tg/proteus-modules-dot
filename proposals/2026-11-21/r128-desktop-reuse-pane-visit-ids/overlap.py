"""Check frozen Desktop receipts through #447 and select only admitted tabs hunks."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root,out=map(Path,sys.argv[1:])
sha=lambda b:hashlib.sha256(b).hexdigest()
roster=(root/"r126/startup/roster.json").read_bytes()
assert sha(roster)=="68f6665a5cc3c2f9a9239fd2c3f0f4821cb521b8b6ab9906ffc5eb58685a0e2e"
r=json.loads(roster)
assert r["exact_total"]==203 and r["already_materialized_count"]==150
last=json.loads((root/"r126/published.json").read_bytes())
assert last["number"]==447 and last["head"]=="fb0828ef0f5244eca6b2672480965d647a05841b"
assert last["source_sha256"]=="0fbae273408cef0ff630f1ed4ab412f23d4073db1e9b44db75e1e77af4f4ba9f"
base="b6a7ec2d8d7e486c8aba01291aa8c89774c4cded"
old,new="already_in_anchor_do_not_reapply","ordered_overlays_apply_only_if_admitted"
r[new].append(dict(pr=447,component="desktop",upstream=base,hard_requirements=[],
                  source_path="r126/desktop/packet/source.patch",source_sha256=last["source_sha256"]))
checked,crate_hits,pane_hits,applied=[],[],[],[]
for group in (old,new):
    for row in r[group]:
        if row["component"]!="desktop": continue
        p=(root/row["source_path"]).resolve(strict=True)
        raw=p.read_bytes()
        assert row["upstream"]==base and sha(raw)==row["source_sha256"],row["pr"]
        changes=subprocess.check_output(["git","apply","--numstat","-z",str(p)])
        files=[x.split(b"\t",2)[2] for x in changes.split(b"\0") if x]
        assert len(set(files))==len(files)==raw.count(b"\ndiff --git ")+raw.startswith(b"diff --git ")
        assert b"LICENSE-GPL" not in files
        if b"crates/tabs/src/pane.rs" in files:
            assert row["pr"]==267
            pane_hits.append(row["pr"])
        if any(f.startswith(b"crates/tabs/") for f in files):
            crate_hits.append(row["pr"])
            if group==new:
                assert not row["hard_requirements"]
                applied.append((row["pr"],p))
        checked.append(row["pr"])
assert len(set(checked))==len(checked)==62 and checked[-1]==447
assert crate_hits==[267,318,440,444] and pane_hits==[267]
assert [n for n,_ in applied]==[440,444]
out.write_text("".join(str(p)+"\n" for _,p in applied))
print("PASS 62 selected Desktop receipt hashes through #447; pane.rs anchored #267 is_pinned only; scoped #440/#444 tabs hunks")
