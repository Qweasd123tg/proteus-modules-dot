#!/usr/bin/env python3
"""Restore the exact M404 scoped model, apply/revert the patch, and rerun native comparisons."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,subprocess,tempfile,sys
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def obj(p):return json.loads(p.read_bytes())
LABEL={'large-at-limit','small-over-cap','four-large-over-cap','root-tool','unknown-thread-tool','completed-child-tool','new-running-duplicate'}
def outcome(log):
    j=re.search(r'test result: ok\. (\d+) passed; 0 failed;',log)
    assert j,log
    mem=re.findall(r'M404_TOOL (\S+) (\d+) (\d+) (-?\d+) (\d+) (\d+) (\d+) (\d+) (\d+)',log)
    assert {v[0] for v in mem}==LABEL and len(mem)==len(LABEL),mem
    keys=('requests','gross_bytes','net_bytes','peak_bytes','max_request','wire_bytes','rows','model_digest')
    return {'tests':int(j[1]),'route':{label:dict(zip(keys,map(int,nums),strict=True)) for label,*nums in mem}}
def same(before,after):
    assert after['tests']==before['tests']+1
    for label,a in before['route'].items():
        b=after['route'][label]
        for k in ('net_bytes','wire_bytes','rows','model_digest'):
            assert a[k]==b[k],(label,k)
        if label in ('four-large-over-cap','small-over-cap'):
            assert b['requests']<a['requests'] and b['gross_bytes']<a['gross_bytes']
        else:
            assert a==b,(label,a,b)
def prepare(root,r):
    data=base64.b64decode(b''.join((P/n).read_bytes().strip() for n in r['capsule_parts']),validate=True)
    assert sha(data)==r['capsule_sha256']
    s={n:v.encode() for n,v in json.loads(gzip.decompress(data)).items()}
    assert {n:oid(v) for n,v in s.items()}==r['source_blobs']
    assert len([n for n in s if n.startswith('crates/proteus-contracts/')])==113
    assert b'.apply_runtime(envelope.thread_id, &envelope.event);' in s['src/ui/chat/pump.rs']
    assert b'session.transcript.stamp(change, envelope.timestamp_ms);' in s['src/ui/chat/pump.rs']
    assert b'MAX_SUBAGENT_TOOLS: usize = 64;' in s['src/transcript/mod.rs']
    assert b'Arc::make_mut(subagent).tools.push(tool);' in s['src/transcript/mod.rs']
    patch=(P/'source.patch').read_bytes()
    assert sha(patch)==r['patch_sha256']
    c=obj(P/'composition.json')
    assert c['composition']['642']['requires_applied_first']
    assert c['composition']['645']['disjoint_both_orders_equal']
    sand=root/'apply-check'
    sand.mkdir()
    for n,v in s.items():
        f=sand/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(v)
    apply=lambda *opts:subprocess.run(['git','apply','--whitespace=error',*opts,'-'],cwd=sand,input=patch,check=True)
    apply('--check');apply()
    assert {n:oid((sand/n).read_bytes()) for n in c['candidate']}==c['candidate']
    apply('-R');assert all((sand/n).read_bytes()==v for n,v in s.items())
    apply()
    for arm in ('stock','candidate'):
        lift(s if arm=='stock' else {n:(sand/n).read_bytes() for n in s},root/arm,P,root/'shared')
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--vendor',type=Path,required=True)
    p.add_argument('--target-dir',type=Path)
    p.add_argument('--source-only',action='store_true')
    a=p.parse_args()
    for line in (P/'SHA256SUMS').read_text().splitlines():
        h,n=line.split(None,1);assert sha((P/n).read_bytes())==h,n
    r=obj(P/'receipt.json')
    cargo=['cargo','--offline','--config','source.crates-io.replace-with="verified"',
           '--config',f'source.verified.directory="{a.vendor.resolve()}"']
    with tempfile.TemporaryDirectory(prefix='m404-capped-request-replay-') as tmp:
        root=Path(tmp);prepare(root,r)
        if a.source_only:
            print('M404 exact scoped source, dependency edge, patch and inverse OK')
            return
        assert subprocess.check_output(['rustc','--version'],text=True).strip()==r['toolchain']
        for mode in ('default','preserve_order'):
            controls=[]
            for side in ('stock','candidate'):
                args=['--features','preserve_order'] if mode=='preserve_order' else []
                env={**os.environ,'CARGO_TARGET_DIR':str(a.target_dir.resolve() if a.target_dir else root/'target'),
                     'CARGO_HOME':str(root/'cargo-home'),'CARGO_INCREMENTAL':'0'}
                p=subprocess.run(cargo+['test','--locked','--lib','-j2',*args,'--','--test-threads=1','--nocapture'],
                                 env=env,cwd=root/side,capture_output=True,text=True)
                if p.returncode:print(p.stdout+p.stderr,flush=True)
                p.check_returncode()
                result=outcome(p.stdout)
                assert result==r['runs'][side][mode],(side,mode,result)
                controls.append(result)
                print(side,mode,result['tests'],result['route']['four-large-over-cap'],flush=True)
            same(*controls)
if __name__=='__main__':main()
