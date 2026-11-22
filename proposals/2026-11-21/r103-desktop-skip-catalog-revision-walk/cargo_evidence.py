"""Select the exact fresh test in Cargo JSON, bind fixture inputs and capture receipts."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def inputs(src):
    return {x.relative_to(src).as_posix():sha(x) for x in sorted(src.rglob("*"))
            if x.is_file() and x.relative_to(src).parts[0] != "build"}

def tool(name):
    exe=Path(shutil.which(name)).resolve(strict=True)
    return {"sha256":sha(exe), "version":subprocess.check_output([exe,"--version"],text=True).strip()}

verb, root, prefix, *rest=sys.argv[1:]
root,prefix=Path(root).resolve(strict=True),Path(prefix).resolve()

def out(suffix): return Path(f"{prefix}.{suffix}")

if verb=="snapshot":
    out("inputs").write_text(json.dumps(inputs(root),sort_keys=True)+"\n")
    sys.exit()
assert verb=="run"
stamp,patch,*fixture=rest
packages=Path(fixture[0]).resolve(strict=True)
bound=json.loads(out("inputs").read_text())
assert bound==inputs(root)
records=[json.loads(line) for line in out("cargo-json").read_text().splitlines()]
assert [x["success"] for x in records if x.get("reason")=="build-finished"]==[True]
name="desktop_catalog_inventory_probe"
selected,=(a for a in records if a.get("reason")=="compiler-artifact" and
           a["target"]["name"]==name and a["target"]["kind"]==["lib"] and a["profile"]["test"])
assert Path(selected["manifest_path"]).resolve()==root/"Cargo.toml"
assert Path(selected["target"]["src_path"]).resolve()==root/"src/lib.rs"
assert selected["fresh"] is False and selected["profile"]["opt_level"]=="0"
exe=Path(selected["executable"]).resolve(strict=True)
warm=Path(os.environ["CARGO_TARGET_DIR"]).resolve(strict=True)
assert exe.parent==warm/"debug/deps" and re.fullmatch(name+"-[0-9a-f]+",exe.name)
lock_contracts="7cbc7206f03fac130d05bed2844de275476fedc8"
dep,=(x for x in records if x.get("reason")=="compiler-artifact" and x["target"]["name"]=="proteus_contracts")
assert dep["package_id"]==f"git+https://github.com/Proteus-harness/Proteus-core.git?rev={lock_contracts}#proteus-contracts@0.1.0-alpha.2"
before=sha(exe)
with out("stdout").open("wb") as stdout,out("stderr").open("wb") as stderr:
    run=subprocess.run([str(exe),"--test-threads=1","--nocapture"],cwd=root,
                       stdout=stdout,stderr=stderr,env=dict(os.environ,R103_PACKAGES=str(packages)))
if run.returncode:
    print(out("stdout").read_text(),out("stderr").read_text())
    sys.exit(run.returncode)
names=[l.removeprefix("test ").removesuffix(" ... ok")
       for l in out("stdout").read_text().splitlines() if l.startswith("test ") and l.endswith(" ... ok")]
expected={
    "declarative::manifest::tests": "declarative/manifest.rs",
    "declarative::manifest::agent_instructions_tests": "declarative/manifest_agent_instructions_tests.rs",
    "declarative::icons::tests": "declarative/icons.rs",
    "catalog::inventory::tests": "catalog/inventory/tests.rs",
    "cases": "cases.rs",
}
full={f"{module}::{fn}" for module,filename in expected.items()
      for fn in re.findall(r"#\[test\]\s+fn (\w+)\(",(root/"src"/filename).read_text())}
assert len(names)==len(full) and set(names)==full,(names,full)
lines=out("stderr").read_text().splitlines()
assert lines.count("ARM "+stamp)==1
trace=[l for l in lines if l.startswith("TRACE ")]
work=[l for l in lines if l.startswith("WORK ")]
assert len(trace)==5 and len(work)==4
out("trace").write_text("\n".join(trace)+"\n")
out("work").write_text("ARM "+stamp+"\n"+"\n".join(work)+"\n")
after=sha(exe)
assert before==after and inputs(root)==bound
row={"arm":stamp, "test":True, "fresh":False, "manifest":"Cargo.toml","source":"src/lib.rs",
     "executable":exe.relative_to(warm).as_posix(),"sha256_before":before,"sha256_after":after,"tests":sorted(names),
     "profile":selected["profile"],"inputs_sha256":bound,"patch_sha256":sha(Path(patch)),
     "trace_sha256":sha(out("trace")),"work_sha256":sha(out("work")),"cargo":tool("cargo"),"rustc":tool("rustc"),
     "contracts_rev":lock_contracts}
out("provenance").write_text(json.dumps(row,sort_keys=True)+"\n")
print(f"PASS fresh artifact {stamp}: {len(names)}/{len(full)} exact manifest, icon subset, inventory and fixture tests")
