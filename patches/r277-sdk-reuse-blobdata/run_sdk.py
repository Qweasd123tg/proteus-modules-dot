"""Build fresh SDK unit tests in an isolated workspace with the native worker dependency pins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
import stage_sdk_tests as overlay

SDK='crates/proteus-module-sdk'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(cmd, cwd, env):
    result=subprocess.run(cmd,cwd=cwd,env=env,text=True,capture_output=True)
    if result.returncode: raise RuntimeError(f"{cmd}:\n{result.stderr}\n{result.stdout}")
    return result.stdout

def stage(arms,w):
    original_lock=arms[0]/'Cargo.lock'
    assert original_lock.read_bytes()==(arms[1]/'Cargo.lock').read_bytes()
    for label,arm in zip(('stock','candidate'),arms):
        root=w/label
        shutil.copytree(arm,root)
        p=root/'Cargo.toml'; a=p.read_text()
        old='members = ["components/session-storage-module", "storage/session-storage"]'
        assert a.count(old)==1
        a=a.replace(f', "{SDK}"','').replace(old,old[:-1]+f', "{SDK}"]')
        p.write_text(a)
        p=root/'Cargo.lock'; a=p.read_text()
        tag='name = "proteus-module-sdk"'
        i=a.index(tag); j=a.index('\n\n',i)
        assert a[i:j].count(' "proteus-module-protocol",\n')==1
        block=a[i:j].replace(' "proteus-module-protocol",\n',' "proteus-module-protocol",\n "proteus-process-host",\n')
        a=a[:i]+block+a[j:];p.write_text(a)
        old=tomllib.loads(original_lock.read_text())
        [d]=[p for p in old['package'] if p['name']=='proteus-module-sdk']
        d['dependencies'].insert(d['dependencies'].index('proteus-module-protocol')+1,'proteus-process-host')
        assert old==tomllib.loads(a),'only dev-dependency edge changes in isolated lock'
        overlay.run(root,label=='candidate')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('stock','candidate','work','vendor','toolchain','target'):
        p.add_argument(f'--{arg}',type=lambda x:Path(x).resolve(),required=True)
    a=p.parse_args()
    w=a.work;w.mkdir(); (w/'cargo-home').mkdir()
    stage((a.stock,a.candidate),w)
    env={'PATH':str(a.toolchain)+os.pathsep+'/usr/bin:/bin','HOME':str(w/'cargo-home'),'CARGO_HOME':str(w/'cargo-home'),
         'CARGO_TARGET_DIR':str(a.target),'CARGO_BUILD_JOBS':'3','RUSTC':str(a.toolchain/'rustc'),'LC_ALL':'C.UTF-8'}
    cmd=[a.toolchain/'cargo','--offline','--locked','--config','source.crates-io.replace-with="verified"',
         '--config','source.verified.directory='+json.dumps(str(a.vendor))]
    records={}
    for mode in ('default','preserve_order'):
        features=['--features','serde_json/preserve_order'] if mode=='preserve_order' else []
        hashes={}
        for label in ('stock','candidate'):
            root=w/label; manifest=root/SDK/'Cargo.toml'
            run(cmd+['clean','--release','-p','proteus-module-sdk'],root,env)
            graph=run(cmd+['tree','-p','proteus-module-sdk','-e','features','-i','serde_json',*features],root,env)
            assert ('serde_json feature "preserve_order"' in graph)==bool(features)
            (w/f'{label}-{mode}.tree').write_text(graph)
            js=run(cmd+['test','-p','proteus-module-sdk','--lib','--release','--no-run','--message-format=json',*features],root,env)
            (w/f'{label}-{mode}.jsonl').write_text(js)
            [artifact]=[r for ln in js.splitlines() if ln.startswith('{') and
                (r:=json.loads(ln)).get('reason')=='compiler-artifact' and r['target']['name']=='proteus_module_sdk'
                and r['profile']['test'] and r.get('executable')]
            assert not artifact['fresh'] and Path(artifact['manifest_path'])==manifest
            assert Path(artifact['target']['src_path'])==root/SDK/'src/lib.rs'
            frozen=w/f'{label}-{mode}-sdk-tests';shutil.copy2(artifact['executable'],frozen)
            hashes[label]=sha(frozen)
            out=run([frozen,'r277_blob','--nocapture','--test-threads=1'],w,env)
            want=3 if label=='stock' else 4
            assert f'test result: ok. {want} passed; 0 failed' in out
            assert out.count('R277_OWN')==18 and out.count('R277_PAUSED')==1
            (w/f'{label}-{mode}.log').write_text(out)
            print(label,mode,out,flush=True)
        assert len(set(hashes.values()))==2
        records[mode]=hashes
    (w/'verification.json').write_text(json.dumps({
        'mode_test_binary_sha256':records, 'isolated_sdk_test_lock_sha256':sha(w/'stock/Cargo.lock'),
        'worker_lock_sha256':sha(a.stock/'Cargo.lock'),
        'patch_sha256':sha(Path(__file__).resolve().parent/'source.patch')},indent=2)+'\n')
if __name__=='__main__':main()
