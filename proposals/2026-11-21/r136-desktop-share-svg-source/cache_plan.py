"""Verify the exact crate closure; optional stage only admitted archives/index entries."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tomllib

verb, root, manifest, *other = sys.argv[1:]
root, manifest = Path(root), Path(manifest)
assert (verb, len(other)) in {("check", 0), ("stage", 1)}
dest = Path(other[0]) if other else None
if dest:
    assert not dest.exists() and (root/"r136/desktop/private") in dest.resolve().parents
    dest.mkdir()
desktop=root/"r52/desktop/cargo"
donor=Path("/tmp")/"r47ext/cargo"
registry="index.crates.io-1949cf8c6b5b557f"
sealed=tomllib.loads((root/"r64/m150-source/desktop/Cargo.lock").read_text())["package"]
ident=lambda p: (p["name"],p["version"],p.get("source"),p.get("checksum"))
locked=tomllib.loads(manifest.read_text())["package"]
exact={ident(p) for p in locked if "source" in p}
assert len(exact)==13 and exact<={ident(p) for p in sealed}
assert len(exact)==len({t[0] for t in exact})
checks=[]
for name,version,source,checksum in sorted(exact):
    assert source=="registry+https://github.com/rust-lang/crates.io-index"
    relative=f"1/{name}" if len(name)==1 else (f"2/{name}" if len(name)==2 else
             (f"3/{name[0]}/{name}" if len(name)==3 else f"{name[:2]}/{name[2:4]}/{name}"))
    area=donor if name=="roxmltree" else desktop
    arc=Path(f"registry/cache/{registry}/{name}-{version}.crate")
    ent=Path(f"registry/index/{registry}/.cache/{relative}")
    assert hashlib.sha256((area/arc).read_bytes()).hexdigest()==checksum
    b=(area/ent).read_bytes()
    entries=[json.loads(chunk) for chunk in b.split(b"\0") if chunk.startswith(b'{"name":')]
    row,=[p for p in entries if p["name"]==name and p["vers"]==version]
    assert row["cksum"]==checksum and not row["yanked"]
    if name=="roxmltree":
        assert version=="0.21.1" and {dep["name"] for dep in row["deps"]}=={"memchr"}
    checks += [(area,arc),(area,ent)]
config=Path(f"registry/index/{registry}/config.json")
config_bytes=(desktop/config).read_bytes()
assert hashlib.sha256(config_bytes).hexdigest()=="5b943a2c6f7eb743f7308aba07bdbb47d9ae44aafecd832d7f15df186afbafb3"
checks += [(desktop, config)]
size = sum((home/path).stat().st_size for home,path in checks)
assert size<4*1024*1024,(size,len(checks))
if dest:
    for home,path in checks:
        d=dest/path
        d.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(home/path,d)
        assert d.read_bytes()==(home/path).read_bytes()
print("PASS 13 exact locked crates; archives and individual index entries only; raw bytes",size,verb)
