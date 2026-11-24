"""Reproduce the bounded Desktop/Native Core SSE codec proof."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,sys,tempfile,subprocess
sys.dont_write_bytecode=True
from lift import lift,between
p=Path(__file__).resolve().parent
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def audit(s):
 c=s['core-sse.rs'];a=s['desktop-api.rs'];boot=s['desktop-startup.rs']
 assert 'b"event: output\\ndata: "' in c and 'frame.extend_from_slice(b"\\n\\n")' in c
 assert 'let mut events = server.subscribe_session();' in c and 'let output = StdioOutput::Event' in c
 assert 'const SSE_HEARTBEAT_SECS' in c and 'Bytes::from_static(b": connected\\n\\n")' in c
 assert 'request.call()?' in a and 'reader: BufReader::new(Box::new(response.into_body().into_reader()))' in a
 assert 'match api.events(&session_dir)' in s['desktop-connection.rs'] and 'match stream.next()' in s['desktop-connection.rs']
 assert 'connection::spawn_pump(api.clone(), dir.clone())' in boot
 assert s['desktop-chat.rs'].index('take_initial_events(&events)')<s['desktop-chat.rs'].index('apply_batch(initial, cx)')
 for file,label in [('app_protocol.rs','pinned-desktop-app-protocol.rs'),('app_protocol/live.rs','live.rs'),('app_protocol/transcript.rs','transcript.rs')]:
  assert s['crates/proteus-contracts/src/'+file]==s[label]
def outcomes(data):
 assert 'test result: ok. 2 passed; 0 failed;' in data
 out={label:[int(n) for n in row] for label,*row in re.findall(r'ALLOC (\S+) (\d+) (\d+) (\d+)',data)}
 assert set(out)=={'buffered-50','fragmented-50'}
 parity=re.findall(r'PARITY (\d+) (\d+)',data)
 assert len(parity)==1 and parity[0][0]=='543'
 return {'allocation':[out['buffered-50'],out['fragmented-50']],'parity':list(map(int,parity[0]))}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--vendor',type=Path);args=ap.parse_args()
 r=json.loads((p/'receipt.json').read_bytes())
 archive=base64.b64decode(b''.join((p/f).read_bytes().strip() for f in r['shards']))
 assert sha(archive)==r['capsule_sha256']
 s=json.loads(gzip.decompress(archive))
 assert {n:oid(t.encode()) for n,t in s.items()}==r['sources']
 audit(s)
 pt=(p/'source.patch').read_bytes();lock=(p/'Cargo.lock').read_text()
 assert sha(pt)==r['patch_sha256'] and sha(lock.encode())==r['projected_lock_sha256']
 cargo=['cargo']
 if args.vendor:
  cargo+=['--offline','--config','source.crates-io.replace-with="verified"','--config',f'source.verified.directory="{args.vendor.resolve()}"']
 pre=s['desktop-api.rs'].encode();post=r['candidate_git_blob']
 with tempfile.TemporaryDirectory() as tmp:
  base=Path(tmp)
  for side in ('stock','candidate'):
   d=base/side;prod=d/'product';api=prod/'src/api/mod.rs'
   api.parent.mkdir(parents=True);api.write_bytes(pre)
   if side=='candidate':
    for opt in (['--check'],[]):
     subprocess.run(['git','apply','--whitespace=error',*opt,'-'],cwd=prod,input=pt,check=True)
    assert oid(api.read_bytes())==post
    subprocess.run(['git','apply','-R','-'],cwd=prod,input=pt,check=True)
    assert api.read_bytes()==pre
    subprocess.run(['git','apply','-'],cwd=prod,input=pt,check=True)
   for n,b in s.items():
    if n.startswith('crates/proteus-contracts/'):
     path=d/n;path.parent.mkdir(exist_ok=True,parents=True);path.write_text(b)
   lift(s,api.read_bytes(),d/'src',p)
   (d/'Cargo.toml').write_text((p/'Cargo.toml').read_text().replace('desktop-native-sse-proof',f'desktop-native-sse-proof-{side}',1))
   (d/'Cargo.lock').write_text(lock.replace('desktop-native-sse-proof-stock',f'desktop-native-sse-proof-{side}',1))
   for mode in ('default','preserve_order'):
    feat=['--features','preserve_order'] if mode=='preserve_order' else []
    env={**os.environ,'CARGO_TARGET_DIR':str(base/'target'),'CARGO_INCREMENTAL':'0'}
    run=subprocess.run(cargo+['test','--locked','--lib',*feat,'--','--test-threads=1','--nocapture'],cwd=d,env=env,capture_output=True,text=True)
    if run.returncode:print(run.stdout+run.stderr,flush=True)
    run.check_returncode()
    got=outcomes(run.stdout)
    assert got==r['runs'][side][mode],(side,mode,got)
    print(side,mode,got,flush=True)
if __name__=='__main__':main()
