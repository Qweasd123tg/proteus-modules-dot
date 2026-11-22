"""Verify the exact selected Desktop prefix; stage only three tabs overlays."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root,out=map(Path,sys.argv[1:])
sha=lambda b:hashlib.sha256(b).hexdigest()
roster=(root/"r131/startup/roster.json").read_bytes()
assert sha(roster)=="c41c6901d1281c7cd129e41cc493408776f9d02843f51588997d87abb0fd396a"
r=json.loads(roster)
assert r["exact_total"]==207 and r["already_materialized_count"]==150
receipt=(root/"r128/published.json").read_bytes()
assert sha(receipt)=="b48982a13648f2bef7f752801e5b76343f4fae76484c1cfff43bad81b7458917"
last=json.loads(receipt)
assert last["number"]==449 and last["head"]=="95120fcbd4a27376bdf136d1e5e3dac5197e8ac5"
assert last["source_sha256"]=="ea4efcb183fa3425c1be5946bc789dfdb0c441b32bff1f105ee7c59008ace25a"
base="b6a7ec2d8d7e486c8aba01291aa8c89774c4cded"
old,new="already_in_anchor_do_not_reapply","ordered_overlays_apply_only_if_admitted"
checked,crate_hits,applied=[],[],[]
for group in (old,new):
    for row in r[group]:
        if row["component"]!="desktop": continue
        p=(root/row["source_path"]).resolve(strict=True)
        raw=p.read_bytes()
        assert row["upstream"]==base and sha(raw)==row["source_sha256"],row["pr"]
        changes=subprocess.check_output(["git","apply","--numstat","-z",str(p)])
        files=[x.split(b"\t",2)[2] for x in changes.split(b"\0") if x]
        assert len(set(files))==len(files)==raw.count(b"\ndiff --git ")+raw.startswith(b"diff --git ")
        assert not {b"src/ui/workspace.rs",b"src/ui/"+b"workspace/startup.rs",b"LICENSE-GPL"}.intersection(files)
        if any(f.startswith(b"crates/tabs/") for f in files):
            crate_hits.append(row["pr"])
            if group==new:
                assert not row["hard_requirements"]
                applied.append((row["pr"],p))
        if row["pr"]==449:
            assert row["source_sha256"]==last["source_sha256"]
        checked.append(row["pr"])
assert len(set(checked))==len(checked)==63 and checked[-1]==449
assert crate_hits==[267,318,440,444,449]
assert [n for n,_ in applied]==[440,444,449]
out.write_text("".join(str(p)+"\n" for _,p in applied))
print("PASS 63 selected Desktop receipt hashes through #449; no Workspace startup method overlap; scoped #440/#444/#449 tabs")
