"""Replay paired native ureq history body readers using authenticated M387 source slices."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,subprocess,tempfile,sys
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent

def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def outcome(log):
    assert 'test result: ok. 4 passed; 0 failed;' in log
    items=re.findall(r'BODY (\S+) '+' '.join([r'(\d+)']*9),log)
    assert len(items)==19, len(items)
    errors=re.findall(r'ERROR (\S+) ([^\n]+)',log);assert len(errors)==8,len(errors)
    return {'wire':{label:list(map(int,nums[:5])) for label,*nums in items},'errors':dict(errors),
            'ambient_tcp_allocator_samples':{label:list(map(int,nums[5:])) for label,*nums in items}}
def comparable(data):
    return {k:v for k,v in data.items() if k!='ambient_tcp_allocator_samples'}

def audit(s):
    a=s['src/api/mod.rs']
    assert 'fn buffered_output(&mut self)' in a and 'pub fn initial_history_page(' in a and 'pub fn history_page(' in a
    assert '.header("Authorization", format!("Bearer {}", self.token))' in a
    assert 'Ok(serde_json::from_str(&body)?)' in a
    assert 'get("/history/page", Some(session_dir))' in a
    assert 'api.initial_history_page(&dir)' in s['src/ui/chat/readonly.rs']
    assert 'api.history_page(&dir, &requested)' in s['src/ui/chat/history.rs']
    assert 'let (row, live) = candidates.next()?;' in s['src/transcript/subagent.rs']
    assert 'drop(self.entries.splice(..0, incoming));' in s['src/transcript/mod.rs']
    assert '    let body = Full::new(body).boxed_unsync();' in s['crates/proteus-core/src/app_server/http/responses.rs']
    assert 'Ok(body) => response_with_body(status, "application/json", Bytes::from(body))' in s['crates/proteus-core/src/app_server/http/responses.rs']
    assert '"/history/page" => json_response(' in s['crates/proteus-core/src/app_server/http/reads.rs']
    assert 'read_model::transcript_page(&store, before, revision.as_deref())' in s['crates/proteus-core/src/app_server/http/sessions.rs']
    assert 'let start = end.saturating_sub(50);' in s['crates/proteus-core/src/app_server/read_model.rs']
    assert 'const PAGE_ROWS: usize = 50;' in s['crates/proteus-core/src/core/session_store/remote/view/cache.rs']

def main():
    p=argparse.ArgumentParser();p.add_argument('--vendor',type=Path);a=p.parse_args()
    r=json.loads((P/'receipt.json').read_bytes())
    dat=base64.b64decode(b''.join((P/n).read_bytes().strip() for n in r['source_shards']))
    assert sha(dat)==r['capsule_hash']
    s=json.loads(gzip.decompress(dat));assert {n:oid(v.encode()) for n,v in s.items()}==r['source_blobs'];audit(s)
    patch=(P/'source.patch').read_bytes();assert sha(patch)==r['patch_sha256']
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
            name=f'desktop-history-buffer-proof-{side}'
            (d/'Cargo.toml').write_text((P/'Cargo.toml').read_text().replace('desktop-history-buffer-proof',name))
            (d/'Cargo.lock').write_text(lock.replace('desktop-history-buffer-proof',name))
            for mode in ('default','preserve_order'):
                args=['--features','preserve_order'] if mode=='preserve_order' else []
                env={**os.environ,'CARGO_TARGET_DIR':str(root/'target')}
                p=subprocess.run(cargo+['test','--release','--locked',*args,'--','--test-threads=1','--nocapture'],env=env,cwd=d,capture_output=True,text=True)
                if p.returncode:print(p.stdout+p.stderr,flush=True)
                p.check_returncode()
                data=outcome(p.stdout)
                assert comparable(data)==comparable(r['runs'][side][mode]),(side,mode,data)
                print(side,mode,len(data['wire']),'native loopback responses;',data['wire']['first'],data['wire']['older'],flush=True)
if __name__=='__main__':main()
