"""Prepare exact paired source proof; this script does not fetch, compile or execute."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
PACKET=Path(__file__).resolve().parent
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
checkout, target=map(lambda x:Path(x).resolve(),sys.argv[1:])
pins=json.loads((PACKET/'source-pins.json').read_text())['files']
source_path='src/ui/chat/images/decode.rs'
for rel,x in pins.items():
    b=(checkout/rel).read_bytes()
    assert [len(b),oid(b)]==x[1:],rel
target.mkdir(parents=True,exist_ok=False)
candidate=target/source_path
candidate.parent.mkdir(parents=True)
stock=(checkout/source_path).read_bytes()
candidate.write_bytes(stock)
subprocess.run(['git','apply','--whitespace=error',str(PACKET/'source.patch')],cwd=target,check=True)
new=candidate.read_bytes()
assert oid(new)==json.loads((PACKET/'receipt.json').read_text())['source']['after_git_oid']
probe=b"\n#[cfg(test)]\npub(super) fn thumbnail_probe(image: DynamicImage, edge: u32) -> image::RgbaImage { thumbnail(image, edge) }\n"
for arm,data in [('stock',stock),('candidate',new)]:
    folder=target/'src'/arm
    folder.mkdir()
    (folder/'mod.rs').write_bytes(data+probe)
    shutil.copyfile(checkout/'src/ui/chat/images/decode/tests.rs',folder/'tests.rs')
    for name in sorted(x for x in pins if '/decode/testdata/' in x):
        out=folder/'testdata'/Path(name).name
        out.parent.mkdir(exist_ok=True)
        shutil.copyfile(checkout/name,out)
for src,dst in [('native-proof.rs','src/lib.rs'),('proof.Cargo.toml','Cargo.toml'),('proof.Cargo.lock','Cargo.lock')]:
    shutil.copyfile(PACKET/src,target/dst)
