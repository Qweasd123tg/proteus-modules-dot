#!/usr/bin/env python3
"""Rehydrate the exact headless M406 tabs crate and replay the first-window clone boundaries."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,subprocess,tempfile,tomllib

P=Path(__file__).resolve().parent
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(p.read_bytes())
names=('requests','gross_bytes','net_bytes','peak_added_bytes','largest','wire_bytes','root_count','shared_roots','wire_digest')
def outcome(log):
    tests=re.search(r'test result: ok\. (\d+) passed; 0 failed;',log)
    assert tests,log
    controls={}
    for line in log.splitlines():
        if 'M406_TABS ' in line:
            label,*v=line.split('M406_TABS ',1)[1].split()
            assert label not in controls and len(v)==len(names),line
            controls[label]=dict(zip(names,map(int,v),strict=True))
    st=re.findall(r'M406_STATE (\d+) (\d+)',log)
    assert len(controls)==8 and len(st)==1,(controls,st)
    return {'tests':int(tests[1]),'route':controls,'mutation_and_visit_order':list(map(int,st[0]))}
def check(a,b):
    assert b['tests']==a['tests']+1 and a['mutation_and_visit_order']==b['mutation_and_visit_order']
    for k,c in a['route'].items():
        d=b['route'][k]
        for key in ('wire_bytes','root_count','wire_digest'):
            assert c[key]==d[key],(k,key)
        assert c['shared_roots']==0,k
        if k.startswith('empty'):
            assert c==d,k
        elif k.endswith('first-window') or k=='live-republish':
            assert d['net_bytes']<c['net_bytes'],k
            assert d['shared_roots']==d['root_count'],k
        elif k=='single-area-retarget':
            assert d['shared_roots']==d['root_count']-1

def run(root,vendor,target):
    q=load(P/'receipt.json');c=load(P/'composition.json')
    for line in (P/'SHA256SUMS').read_text().splitlines():
        h,n=line.split(None,1);assert sha((P/n).read_bytes())==h,n
    lock=(P/'Cargo.lock').read_bytes();assert sha(lock)==c['native_lock_sha256']
    for spec in tomllib.loads(lock.decode())['package']:
        if 'checksum' not in spec: continue
        n=spec['name']+'-'+spec['version']
        meta=load(vendor/n/'.cargo-checksum.json')
        assert meta['package']==spec['checksum']==c['registry_pins'][n],n
        for name,h in meta['files'].items():
            assert sha((vendor/n/name).read_bytes())==h,(n,name)
    b=base64.b64decode(b''.join((P/n).read_bytes().strip() for n in q['source_parts']),validate=True)
    assert sha(b)==q['source_sha256']
    s={n:v.encode()for n,v in json.loads(gzip.decompress(b)).items()}
    assert {n:oid(v) for n,v in s.items()}==q['source_oids']
    assert b'windows.register(cx.weak_entity(), spaces.clone())' in s['src/ui/workspace.rs']
    assert b'let layout = spaces.active_layout().clone();' in s['src/ui/workspace.rs']
    assert b'let mut saved = windows.next()?.1.clone();' in s['src/ui/workspace/windows.rs']
    assert b'*saved = layout.clone();' in s['src/ui/workspace/windows.rs']
    assert b'let mut value = (**previous).clone();' in s['src/ui/prefs.rs']
    sand=root/'check';sand.mkdir()
    for n,v in s.items():
        f=sand/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(v)
    patch=(P/'source.patch').read_bytes()
    assert sha(patch)==c['patch_sha256']
    apply=lambda *opt:subprocess.run(['git','apply','--whitespace=error',*opt,'-'],cwd=sand,input=patch,check=True)
    apply('--check');apply()
    assert all(oid((sand/n).read_bytes())==h for n,h in c['candidate'].items())
    apply('-R');assert all((sand/n).read_bytes()==v for n,v in s.items())
    apply()
    for side in ('stock','candidate'):
        ar=root/side
        ar.mkdir()
        for n,v in s.items():
            if not n.startswith('crates/tabs/'):continue
            f=ar/n.removeprefix('crates/tabs/')
            f.parent.mkdir(parents=True,exist_ok=True)
            f.write_bytes(v if side=='stock' else (sand/n).read_bytes())
        f=ar/'Cargo.toml'
        f.write_text(f.read_text().replace('name = "proteus-tabs"',f'name = "tabs-m406-{side}"')+'''
[features]
preserve_order = ["serde_json/preserve_order"]
[profile.release]
incremental = false
debug = false
''')
        (ar/'Cargo.lock').write_bytes(lock.replace(b'tabs-m406-proof',f'tabs-m406-{side}'.encode()))
        for n in ('fixture.rs','meter.rs'):
            (ar/'src'/n).write_bytes((P/n).read_bytes())
        f=ar/'src/lib.rs'
        with f.open('a') as w:w.write('\n#[cfg(test)]\nmod meter;\n#[cfg(test)]\nmod fixture;\n')
    assert subprocess.check_output(['rustc','--version'],text=True).strip()==q['rustc']
    cargo=['cargo','--offline','--config','source.crates-io.replace-with="verified"',
           '--config',f'source.verified.directory="{vendor}"']
    for mode in ('default','preserve_order'):
        results=[]
        for side in ('stock','candidate'):
            features=['--features','preserve_order'] if mode=='preserve_order' else []
            args=['test','--locked','--release','--lib','-j2',*features,'--','--test-threads=1','--nocapture']
            env={**os.environ,'CARGO_HOME':str(root/'cargo-home'),'CARGO_TARGET_DIR':str(target),'CARGO_INCREMENTAL':'0'}
            p=subprocess.run(cargo+args,cwd=root/side,env=env,capture_output=True,text=True)
            if p.returncode:print(p.stdout+p.stderr)
            p.check_returncode()
            result=outcome(p.stdout)
            assert result==q['runs'][side][mode],(side,mode,result)
            print(side,mode,result['tests'],result['route']['mixed-areas-first-window'],flush=True)
            results.append(result)
        check(*results)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vendor',type=Path,required=True)
    p.add_argument('--target-dir',type=Path)
    a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='m406-headless-tabs-')as t:
        root=Path(t)
        run(root,a.vendor.resolve(),a.target_dir.resolve() if a.target_dir else root/'target')
