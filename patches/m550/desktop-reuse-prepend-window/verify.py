"""Run paired native lifts of the exact M380 page/snapshot reducers."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,subprocess,tempfile,sys
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def outcome(log):
    assert 'test result: ok. 27 passed; 0 failed;' in log
    items=re.findall(r'CASE (\S+) (\d+) (\d+) (\d+) (\d+) (\d+)',log)
    assert len(items)==5
    chain=re.findall(r'CHAIN (\d+) (\d+) (\d+) (\d+)',log);assert len(chain)==1
    edges=re.findall(r'EDGE (\S+) ' + ' '.join([r'(\d+)']*7),log); assert len(edges)==8
    prep=re.findall(r'PREP (\d+) ' + ' '.join([r'(\d+)']*11),log); assert len(prep)==8
    controls=re.findall(r'CONTROL (\S+) ' + ' '.join([r'(\d+)']*5),log); assert len(controls)==3
    return {'case':{label:list(map(int,nums)) for label,*nums in items},'navigation':list(map(int,chain[0])),
            'edges':{label:list(map(int,nums)) for label,*nums in edges},
            'ordinary_older':{step:list(map(int,nums)) for step,*nums in prep},
            'controls':{label:list(map(int,nums)) for label,*nums in controls}}
def audit(s):
    api=s['src/api/mod.rs'];history=s['src/ui/chat/history.rs']
    assert 'struct ChargedRows' in history and 'Option<ChargedRows>' in history  # #621 already present
    assert 'transcript.complete_history_window(live, removed.start - count);' in history  # #616 preimage
    context=s['src/ui/chat/history/context.rs']
    assert 'seek_context(range, self.target).or_else' in context
    assert 'self.rows >= CACHE_ROWS || self.bytes >= CACHE_BYTES' in context
    assert 'fn buffered_output(&mut self)' in api  # already-admitted #613 preimage
    assert 'pub fn history_page(' in api and '"/history/page"' in api and 'Ok(serde_json::from_str(&body)?)' in api
    assert 'api.history_page(&dir, &requested)' in history and 'this.history.accept_page(' in history
    core_session=s['witness/core-http-sessions.rs']
    assert 'fn history_page_json(' in core_session and 'read_model::transcript_page(&store, before, revision.as_deref())' in core_session
    assert 'let start = end.saturating_sub(50);' in s['witness/core-read-model.rs']
    display=s['witness/core-cache.rs']
    assert 'let start = end.saturating_sub(PAGE_ROWS);' in display and 'const PAGE_ROWS: usize = 50;' in display
    assert 'args: call.args.clone(),' in s['witness/core-transcript.rs']
def main():
    a=argparse.ArgumentParser();a.add_argument('--vendor',type=Path);a=a.parse_args()
    r=json.loads((P/'receipt.json').read_bytes())
    dat=base64.b64decode(b''.join((P/n).read_bytes().strip() for n in r['source_shards']))
    assert sha(dat)==r['capsule_hash']
    s=json.loads(gzip.decompress(dat));assert {n:oid(v.encode()) for n,v in s.items()}==r['source_blobs']
    audit(s)
    patch=(P/'source.patch').read_bytes()
    assert sha(patch)==r['patch_sha256']
    lock=(P/'Cargo.lock').read_text()
    cargo=['cargo']
    if a.vendor:
        cargo+=['--offline','--config','source.crates-io.replace-with="verified"','--config',f'source.verified.directory="{a.vendor.resolve()}"']
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for side in ('stock','candidate'):
            d=root/side;source=d/'product'
            for n,v in s.items():
                f=source/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(v)
            if side=='candidate':
                for opts in (['--check'],[]):
                    subprocess.run(['git','apply','--whitespace=error',*opts,'-'],cwd=source,input=patch,check=True)
                assert {n:oid((source/n).read_bytes()) for n in r['candidate_blobs']}==r['candidate_blobs']
                subprocess.run(['git','apply','-R','-'],cwd=source,input=patch,check=True)
                assert all((source/n).read_bytes()==v.encode() for n,v in s.items())
                subprocess.run(['git','apply','-'],cwd=source,input=patch,check=True)
            lift({n:(source/n).read_text() for n in s},d/'src',P)
            name=f'desktop-resident-prepend-proof-{side}'
            (d/'Cargo.toml').write_text((P/'Cargo.toml').read_text().replace('desktop-boot-display-proof',name))
            (d/'Cargo.lock').write_text(lock.replace('desktop-boot-display-proof',name))
            for mode in ('default','preserve_order'):
                args=['--features','preserve_order'] if mode=='preserve_order' else []
                env={**os.environ,'CARGO_TARGET_DIR':str(root/'target')}
                p=subprocess.run(cargo+['test','--release','--locked',*args,'--','--test-threads=1','--nocapture'],env=env,cwd=d,capture_output=True,text=True)
                if p.returncode:print(p.stdout+p.stderr,flush=True)
                p.check_returncode()
                data=outcome(p.stdout)
                assert data==r['runs'][side][mode],(side,mode,data)
                print(side,mode,'27 native model tests',data['ordinary_older']['4'],flush=True)
if __name__=='__main__':main()
