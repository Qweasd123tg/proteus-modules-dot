"""Admit only the exact, newly built, serial Router test executable on this source arm."""
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess,sys

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def inputs(src):
    return {x.relative_to(src).as_posix():sha(x) for x in sorted(src.rglob("*")) if x.is_file()}
def tool(name):
    exe=Path(shutil.which(name)).resolve(strict=True)
    return {"sha256":sha(exe),"version":subprocess.check_output([exe,"--version"],text=True).strip()}

verb, root, prefix, *rest = sys.argv[1:]
root,prefix=Path(root).resolve(strict=True),Path(prefix).resolve()
def out(suffix):return Path(str(prefix)+"."+suffix)
if verb=="snapshot":
    out("inputs").write_text(json.dumps(inputs(root),sort_keys=True)+"\n")
    sys.exit()
assert verb=="run"
stamp,patch=rest
bound=json.loads(out("inputs").read_text())
assert bound==inputs(root)
records=[json.loads(l) for l in out("cargo-json").read_text().splitlines()]
assert [x["success"] for x in records if x.get("reason")=="build-finished"]==[True]
warm=Path(os.environ["CARGO_TARGET_DIR"]).resolve(strict=True)
def artifact(name,manifest,src,kind,test):
    obj,=(o for o in records if o.get("reason")=="compiler-artifact" and o["target"]["name"]==name
            and Path(o["manifest_path"]).resolve()==root/manifest and o["target"]["kind"]==[kind]
            and o["profile"]["test"]==test)
    assert Path(obj["target"]["src_path"]).resolve()==root/src
    assert obj["profile"]["opt_level"]=="0"
    return obj
name="desktop_router_json_bytes_probe"
selected=artifact(name,"Cargo.toml","src/lib.rs","lib",True)
client=artifact("proteus_codex_client","crates/codex-client/Cargo.toml","crates/codex-client/src/lib.rs","lib",False)
assert selected["fresh"] is False and selected["target"]["crate_types"]==["lib"]
assert client["fresh"] is False
rlib,=(Path(v).resolve(strict=True) for v in client["filenames"] if v.endswith(".rlib"))
assert rlib.parent==warm/"debug/deps"
lib_before=sha(rlib)
exe=Path(selected["executable"]).resolve(strict=True)
assert exe.parent==warm/"debug/deps" and re.fullmatch(name+"-[0-9a-f]+",exe.name)
serde,=(o for o in records if o.get("reason")=="compiler-artifact" and o["target"]["name"]=="serde_json" and o["target"]["kind"]==["lib"])
assert ("preserve_order" in serde["features"])==stamp.endswith("/ordered")
assert "float_roundtrip" in serde["features"]
before=sha(exe)
args=[str(exe),"router::","--test-threads=1","--nocapture"]
with out("stdout").open("wb") as stdout,out("stderr").open("wb") as stderr:
    run=subprocess.run(args,cwd=root,stdout=stdout,stderr=stderr)
if run.returncode:
    print(out("stdout").read_text(),out("stderr").read_text())
    sys.exit(run.returncode)
lines=out("stdout").read_text().splitlines()
names=[l.removeprefix("test ").removesuffix(" ... ok") for l in lines if l.startswith("test router::") and l.endswith(" ... ok")]
expected=sorted("router::tests::"+n for n in re.findall(r"#\[test\]\s+fn (\w+)\(",(root/"src/router.rs").read_text()))
expected+=sorted("router::proof::"+n for n in re.findall(r"#\[test\]\s+fn (\w+)\(",(root/"src/cases.rs").read_text()))
assert sorted(names)==sorted(expected) and len(expected)==13, names
errs=out("stderr").read_text().splitlines()
assert errs.count("ARM "+stamp)==1
trace=[l for l in errs if l.startswith("TRACE ")]
work=[l for l in errs if l.startswith("WORK ")]
assert len(trace)==4 and len(work)==5
out("trace").write_text("\n".join(trace)+"\n")
out("work").write_text("ARM "+stamp+"\n"+"\n".join(work)+"\n")
after=sha(exe)
assert before==after and lib_before==sha(rlib) and inputs(root)==bound
record={"arm":stamp,"manifest":"Cargo.toml","source":"src/lib.rs","test":True,"fresh":False,
        "executable":exe.relative_to(warm).as_posix(),"sha256_before":before,"sha256_after":after,
        "client":{"source":"crates/codex-client/src/lib.rs","fresh":False,"rlib_sha256":lib_before},
        "serde_json_features":serde["features"],"profile":selected["profile"],"tests":sorted(names),
        "inputs_sha256":bound,"patch_sha256":sha(Path(patch)),"trace_sha256":sha(out("trace")),
        "work_sha256":sha(out("work")),"cargo":tool("cargo"),"rustc":tool("rustc")}
out("provenance").write_text(json.dumps(record,sort_keys=True)+"\n")
print(f"PASS fresh artifact {stamp}: {len(names)}/{len(names)} Router tests; local transport bound, not run")
