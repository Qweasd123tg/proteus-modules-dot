"""Desktop boot range and image control: isolate native scoped reducers."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,shutil,subprocess,sys,tempfile
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent
def oid(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def sha(data):return hashlib.sha256(data).hexdigest()
def outcome(out):
    lines=re.findall(r'(ROUTE|IMAGE) (\{[^\n]*\})',out)
    cases={};images=None
    for kind,raw in lines:
        j=json.loads(raw)
        if kind=='IMAGE':
            assert images is None
            images=j
        else:
            assert j['tag'] not in cases
            cases[j['tag']]=j
    assert len(cases)==7 and images is not None
    assert 'test result: ok. 5 passed; 0 failed;' in out
    return dict(cases=cases,images=images)
def inputs(r):
    chunks=[(P/f).read_bytes().strip() for f in r['capsule_shards']]
    raw=base64.b64decode(b''.join(chunks))
    assert sha(raw)==r['capsule_compressed_sha256']
    sources=json.loads(gzip.decompress(raw))
    assert {n:oid(s.encode()) for n,s in sources.items()}==r['source_blobs']
    return sources
def audit(s):
    boot=s['src/ui/workspace/startup.rs']
    conn=s['src/connection.rs']
    chat=s['src/ui/chat/mod.rs']
    pump=s['src/ui/chat/pump.rs']
    hist=s['src/ui/chat/history.rs']
    view=s['src/ui/chat/view.rs']
    app=s['vendor/gpui-fast/src/app.rs']
    ctx=s['vendor/gpui-fast/src/app/context.rs']
    assert 'connection::spawn_pump(api.clone(), dir.clone())' in boot
    assert 'match api.events(&session_dir)' in conn and '(0..256).map_while(|_| events.try_recv().ok()).collect()' in conn
    assert chat.index('take_initial_events(&events)')<chat.index('apply_batch(initial, cx)')
    assert 'sent_images: SentImages::default()' in chat
    assert 'BatchItem::Barrier(item) => shown |= self.apply(item, cx)' in pump
    assert 'PumpItem::Event(event) => self.apply_event(*event, cx)' in pump
    assert 'self.sent_images.retain(entries);' in pump
    assert 'crate::startup_trace::first("chat.transcript.render");' in view
    assert 'fn apply_history_changes' in hist and hist.index('self.sync_history_range(cx)')<hist.index('crate::startup_trace::history_window')
    assert 'self.app.notify(self.entity_state.entity_id);' in ctx
    assert 'let result = update(self);\n        self.finish_update();' in app
    assert 'if self.pending_updates == 1 {\n            self.flush_effects();' in app
    assert '.push_back(Effect::Notify { emitter: entity_id });' in app
def cargo_mode(side,mode):
    return [n for n,ok in [('range_candidate',side in ('range','combined')),('images_candidate',side in ('images','combined')),('preserve_order',mode=='preserve_order')] if ok]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--vendor',type=Path);a=ap.parse_args()
    r=json.loads((P/'receipt.json').read_bytes())
    s=inputs(r);audit(s)
    patches={n:(P/f'{n}.patch').read_bytes() for n in ('range','images')}
    assert {n:sha(b) for n,b in patches.items()}==r['patch_sha256']
    cargo=['cargo']
    if a.vendor:
        cargo+=['--offline','--config','source.crates-io.replace-with="verified"','--config',f'source.verified.directory="{a.vendor.resolve()}"']
    target_paths=r['changed_paths']
    with tempfile.TemporaryDirectory() as td:
        work=Path(td)
        for side in ('stock','range','images','combined'):
            d=work/side;prod=d/'product'
            for n,b in s.items():
                f=prod/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(b)
            order=tuple(patches) if side=='combined' else () if side=='stock' else (side,)
            def apply(names,back=False):
                for name in names:
                    for flag in (['--check'],[]):
                        subprocess.run(['git','apply','--whitespace=error',*(['-R'] if back else []),*flag,'-'],cwd=prod,input=patches[name],check=True)
            def verify(case):
                for f in target_paths:
                    assert oid((prod/f).read_bytes())==r['postimage_git_blobs'][case][f],(case,f)
            apply(order);verify(side);apply(reversed(order),True);verify('stock')
            if side=='combined':
                apply(reversed(order));verify(side);apply(order,True);verify('stock')
            apply(order);verify(side)
            lift(prod,P,d/'src')
            for f in ('Cargo.toml','Cargo.lock'):shutil.copyfile(P/f,d/f)
            env={**os.environ,'CARGO_TARGET_DIR':str(work/f'target-{side}')}
            for mode in ('default','preserve_order'):
                features=cargo_mode(side,mode)
                opts=['--features',','.join(features)] if features else []
                run=subprocess.run(cargo+['test','--locked','--release',*opts,'--','--test-threads=1','--nocapture'],cwd=d,env=env,capture_output=True,text=True)
                if run.returncode:print(run.stdout+run.stderr,flush=True)
                run.check_returncode()
                record=outcome(run.stdout)
                assert record==r['runs'][side][mode],(side,mode,record)
                print(side,mode,'5 reducer tests, 7 route controls, cold image allocations',record['images']['cold_requests'],flush=True)
if __name__=='__main__': main()
