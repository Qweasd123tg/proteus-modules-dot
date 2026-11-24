"""Replay exact M398 typed Runtime/Transcript and native history page reducers."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,subprocess,tempfile,sys
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def outcome(log):
    assert 'test result: ok. 80 passed; 0 failed;' in log
    mem=re.findall(r'MEM (\S+) (-?\d+) (\d+) (\d+) (\d+) (\d+)',log);assert len(mem)==4,len(mem)
    rows=re.findall(r'MODEL (\S+) (\d+) (\d+) (\d+) (\d+)',log);assert len(rows)==6,len(rows)
    return {'memory':{label:list(map(int,nums)) for label,*nums in mem},
      'model':{label:list(map(int,nums)) for label,*nums in rows}}
def audit(s):
    h=s['src/ui/chat/history.rs'];t=s['src/transcript/mod.rs'];a=s['src/api/mod.rs']
    assert 'fn read_history_body(body: ureq::Body)' in a  # #632 present
    assert 'transcript.complete_history_window(live, removed.start - count)' in h
    assert 'drop(self.entries.splice(..0, incoming));' in t  # #624 present
    assert 'decode_session(value)?' in s['src/transcript/subagent.rs']  # #628 present
    assert 'pub struct Entry<Tool = Arc<AppTranscriptTool>>' in t  # exact #637 standalone COW
    assert 'families.into_iter().cloned().collect()' in s['vendor/gpui-fast-wgpu/src/cosmic_text_system.rs']  # #639
    assert 'MAX_SUBAGENT_TOOLS: usize = 64;' in t
    assert 'pub subagent: Option<AppTranscriptSubagent>' in s['src/declarative/session.rs']
    assert 'fn update_tool(' in t and 'pub fn apply_runtime(&mut self, thread_id: ThreadId, event: &Event)' in t
    assert '&live.entries()[offset..]' in h and 'this.history.accept_page(' in h
    assert 'api.initial_history_page(&dir)' in s['src/ui/chat/readonly.rs']
    assert 'tools: impl IntoIterator<Item = &\'a AppTranscriptTool>' in s['src/ui/chat/tool_chain.rs']
    assert 'pub tool: Option<AppTranscriptTool>' in s['src/declarative/session.rs']
    assert 'pub struct AppTranscriptPage' in s['crates/proteus-contracts/src/app_protocol/transcript.rs']

def main():
    p=argparse.ArgumentParser();p.add_argument('--vendor',type=Path)
    p.add_argument('--target-dir',type=Path,help='reuse compiled vendored deps safely when short on disk; all source rehydrated')
    a=p.parse_args()
    r=json.loads((P/'receipt.json').read_bytes())
    dat=base64.b64decode(b''.join((P/n).read_bytes().strip() for n in r['source_shards']))
    assert sha(dat)==r['capsule_hash']
    s=json.loads(gzip.decompress(dat));assert {n:oid(v.encode()) for n,v in s.items()}==r['source_blobs'];audit(s)
    patch=(P/'source.patch').read_bytes();assert sha(patch)==r['patch_sha256']
    lock=(P/'Cargo.lock').read_text();assert sha(lock.encode())==r['proof_lock_sha256']
    assert sha((P/'child-use-audit.json').read_bytes())==r['desktop_field_audit_sha256']
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
            name=f'desktop-child-window-proof-{side}'
            (d/'Cargo.toml').write_text((P/'Cargo.toml').read_text().replace('desktop-child-window-proof',name))
            (d/'Cargo.lock').write_text(lock.replace('desktop-child-window-proof',name))
            for mode in ('default','preserve_order'):
                args=['--features','preserve_order'] if mode=='preserve_order' else []
                env={**os.environ,'CARGO_TARGET_DIR':str(a.target_dir.resolve() if a.target_dir else root/'target'),'CARGO_INCREMENTAL':'0'}
                p=subprocess.run(cargo+['test','--locked','--lib','-j2',*args,'--','--test-threads=1','--nocapture'],env=env,cwd=d,capture_output=True,text=True)
                if p.returncode:print(p.stdout+p.stderr,flush=True)
                p.check_returncode()
                data=outcome(p.stdout)
                assert data==r['runs'][side][mode],(side,mode,data)
                print(side,mode,'80 tests',data['memory']['first-older'],data['model']['first-older'],flush=True)
if __name__=='__main__':main()
