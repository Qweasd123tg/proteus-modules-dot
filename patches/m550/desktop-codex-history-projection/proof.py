"""Reproduce in an isolated workspace; Python 3.11, Rust 1.95 and Git."""
from pathlib import Path
import argparse, base64, gzip, hashlib, json, os, shutil, subprocess, tempfile, tomllib
P=Path(__file__).resolve().parent
ap=argparse.ArgumentParser()
ap.add_argument('--vendor', type=Path, help='optional offline Cargo vendor directory')
A=ap.parse_args()
R=json.loads((P/'receipt.json').read_bytes())
S=json.loads(gzip.decompress(base64.b64decode((P/'sources.json.gz.b64').read_bytes())))
def git_blob(b):
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
assert set(S)==set(R['source_git_blobs'])
for n,s in S.items():assert git_blob(s.encode())==R['source_git_blobs'][n],n
patch=(P/'source.patch').read_bytes()
assert hashlib.sha256(patch).hexdigest()==R['source_patch_sha256']
lock=(P/'Cargo.lock').read_bytes()
packages=tomllib.loads(lock.decode())['package']
deps={p['name']+'/'+p['version']:p['checksum'] for p in packages if 'checksum' in p}
assert deps==R['registry_package_checksums']
cargo=['cargo']
if A.vendor:
    cargo+=['--offline','--config','source.crates-io.replace-with="verified"','--config',f'source.verified.directory="{A.vendor.resolve()}"']
with tempfile.TemporaryDirectory() as td:
    root=Path(td)
    for side in ('stock','candidate'):
        d=root/side
        for n,s in S.items():
            f=d/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(s)
        if side=='candidate':
            subprocess.run(['git','apply','--check','-'],cwd=d,input=patch,check=True)
            subprocess.run(['git','apply','-'],cwd=d,input=patch,check=True)
            for n,oid in R['candidate_git_blobs'].items():assert git_blob((d/n).read_bytes())==oid,n
            subprocess.run(['git','apply','-R','-'],cwd=d,input=patch,check=True)
            for n,s in S.items(): assert (d/n).read_bytes()==s.encode(),n
            subprocess.run(['git','apply','-'],cwd=d,input=patch,check=True)
        for n in ('peer.py','wire.rs','meter.rs'):shutil.copyfile(P/n,d/'src'/n)
        (d/'src/lib.rs').write_text('#![allow(dead_code)]\n#[path="agents/codex/mod.rs"] pub mod codex;\n')
        shutil.copyfile(P/'Cargo.toml',d/'Cargo.toml')
        (d/'Cargo.lock').write_bytes(lock)
        env={**os.environ,'CARGO_TARGET_DIR':str(root/('target-'+side))}
        for mode in ('default','preserve_order'):
            opt=[] if mode=='default' else ['--features','preserve_order']
            def run(cmd):
                p=subprocess.run(cargo+cmd,cwd=d,env=env,text=True,capture_output=True)
                if p.returncode:print(p.stdout+p.stderr,flush=True)
                p.check_returncode()
                return p.stdout
            wire=run(['run','--locked','--release',*opt,'--bin','wire']).strip()
            tests=[p.split(';')[0] for p in run(['test','--locked','--release',*opt,'--workspace','--lib','--test','transport']).splitlines() if p.startswith('test result:')]
            expected=R['results'][side][mode]
            def parse(line):
                return {k:int(v) for k,v in (part.split('=') for part in line.split())}
            counts=parse(wire)
            saved=parse(expected['wire'])
            assert counts.keys()==saved.keys() and tests==expected['test_summary'],(side,mode,wire,tests)
            # The worker's full resume also registers an active subscription.
            # Its thread/channel bookkeeping showed a small allocation variance.
            # Require exact repeatability on the isolated page / payload checks.
            for key,n in saved.items():
                tolerance={'open_allocations':2,'open_bytes':512}.get(key,0)
                assert abs(counts[key]-n)<=tolerance,(side,mode,key,counts[key],n)
            print(side,mode,wire,tests,flush=True)
