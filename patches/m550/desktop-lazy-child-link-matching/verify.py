"""Run paired native lifts of exact M384 Core/desktop history model code."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,subprocess,tempfile,sys
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent

def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()

def outcome(log):
    assert 'test result: ok. 36 passed; 0 failed;' in log
    items=re.findall(r'DISPLAY (\S+) '+' '.join([r'(\d+)']*8),log)
    assert len(items)==2
    parity=re.findall(r'PARITY (\d+)',log);assert len(parity)==1
    return {'display':{label:list(map(int,nums)) for label,*nums in items},'overlay_parity_digest':int(parity[0])}

def audit(s):
    hist=s['src/ui/chat/history.rs']
    assert 'struct ChargedRows' in hist
    assert 'transcript.complete_history_window(live, removed.start - count);' in hist
    assert 'drop(self.entries.splice(..0, incoming));' in s['src/transcript/mod.rs']
    api=s['src/api/mod.rs']
    assert 'fn buffered_output(&mut self)' in api and 'self.get("/history/page", Some(session_dir))' in api
    readonly=s['src/ui/chat/readonly.rs']
    pieces=['api.initial_history_page(&dir)','!this.finish_history_request(request, cx)','!workspace.document_current(&document, cx.entity_id())',
            'Ok(page) if page.start + page.messages.len() == page.total','this.history.apply(','this.apply_history_changes(changes, cx)']
    assert [readonly.index(x) for x in pieces] == sorted(readonly.index(x) for x in pieces)
    v=s['src/ui/chat/view.rs'];thread=s['src/ui/chat/thread.rs']
    assert 'self.prepare_turn_stamp(cx);' in v and 'this.render_row(ix, frame_at, window, cx)' in v
    assert 'super::row_layout::row_context(' in v
    assert 'if stamp::hidden(entries, entry)' in thread and 'stamp::turn_end(entries, end, self.complete_stamp_tail())' in thread
    assert 'session: crate::transcript::subagent::task_session(tool),' in thread
    cb='crates/proteus-core/src/app_server/'
    core=s[cb+'http/sessions.rs']
    assert 'fn history_page_json(' in core and 'read_model::transcript_page(&store, before, revision.as_deref())' in core
    assert 'let start = end.saturating_sub(50);' in s[cb+'read_model.rs']
    j=s[cb+'transcript/journal.rs']
    for n in ('tool.metadata["tool"] =','tool.metadata["child_thread_id"] =','tool.metadata["subagent_session"] ='):
        assert n in j
    assert 'subagent: None,' in s[cb+'transcript.rs']
    assert 'fn progress_row(entries: &[super::Entry]' in s['src/transcript/subagent.rs']

def main():
    a=argparse.ArgumentParser();a.add_argument('--vendor',type=Path);a=a.parse_args()
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
            name=f'desktop-task-card-proof-{side}'
            (d/'Cargo.toml').write_text((P/'Cargo.toml').read_text().replace('desktop-boot-display-proof',name))
            (d/'Cargo.lock').write_text(lock.replace('desktop-boot-display-proof',name))
            for mode in ('default','preserve_order'):
                args=['--features','preserve_order'] if mode=='preserve_order' else []
                env={**os.environ,'CARGO_TARGET_DIR':str(root/'target')}
                p=subprocess.run(cargo+['test','--release','--locked',*args,'--','--test-threads=1','--nocapture'],env=env,cwd=d,capture_output=True,text=True)
                if p.returncode:print(p.stdout+p.stderr,flush=True)
                p.check_returncode()
                data=outcome(p.stdout);assert data==r['runs'][side][mode],(side,mode,data)
                print(side,mode,'36 native tests',data['display'],flush=True)
if __name__=='__main__':main()
