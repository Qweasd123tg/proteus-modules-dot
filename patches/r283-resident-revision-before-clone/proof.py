#!/usr/bin/env python3
"""Stage or replay R283. All Core sources and registry inputs must be supplied locally.
Replays are focused native current-thread executables, not full Proteus or Desktop binaries."""
import argparse,hashlib,json,os,shutil,subprocess,sys,tarfile,tomllib
from pathlib import Path,PurePosixPath
P=Path(__file__).resolve().parent;sys.dont_write_bytecode=True
conv='crates/proteus-core/src/core/runtime/conversation.rs'; registry='registry+https://github.com/rust-lang/crates.io-index'
def need(b,e):
 if not b:raise ValueError(e)
def H(b):return hashlib.sha256(b).hexdigest()
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def write(p,b):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
def j(p):return json.loads(p.read_text())
def members(arc,n,m,v,cache):
 need(H(arc.read_bytes())==m,'archive SHA '+n);sums={}; bdir=None if cache is None else cache/n
 with tarfile.open(arc) as t:
  for x in t:
   q=PurePosixPath(x.name)
   need(not q.is_absolute() and q.parts[0]==n and '..' not in q.parts,'unsafe archive path')
   if x.isdir(): continue
   need(x.isfile() and len(q.parts)>1,'non-regular archive member')
   s=str(PurePosixPath(*q.parts[1:]));need(s not in sums and s!='.cargo-checksum.json','duplicate/reserved archive member')
   b=t.extractfile(x).read();sums[s]=H(b)
   if bdir:need((bdir/s).read_bytes()==b,'cached file mismatch: '+n+'/'+s)
   else:
    write(v/n/s,b)
    if x.mode&0o100:(v/n/s).chmod(0o755)
 check=dict(package=m,files=sums)
 if bdir:
  need(j(bdir/'.cargo-checksum.json')==check,'cached checksum manifest')
  need(set(sums)=={str(f.relative_to(bdir)) for f in bdir.rglob('*') if f.is_file() and f.name!='.cargo-checksum.json'},'unexpected cached files '+n)
  (v/n).symlink_to(bdir.resolve(),target_is_directory=True)
 else:write(v/n/'.cargo-checksum.json',json.dumps(check,sort_keys=True).encode())
 return len(sums)
def main(a):
 W=a.work.resolve();S=a.core.resolve();N=W/'native';D=W/'stock';C=W/'candidate'
 spec=j(P/'source-pins.json')
 need(not W.exists() or W.is_dir() and not any(W.iterdir()),'need new or empty --work')
 W.mkdir(exist_ok=True,parents=True)
 for q in ['tmp','home','vendor','cargo-home','evidence','artifacts']: (W/q).mkdir()
 for p,h in spec['source_files'].items():
  b=(S/p).read_bytes();need(blob(b)==h,'wrong Core blob '+p);write(D/p,b)
  if p.startswith(('crates/proteus-contracts/','crates/proteus-session-semantics/')):write(N/p,b)
 for f,h in spec['input_sha256'].items():need(H((P/f).read_bytes())==h,'changed input '+f)
 write(C/conv,(D/conv).read_bytes())
 subprocess.run(['git','apply','--no-index','--check',str(P/'source.patch')],cwd=C,check=True)
 subprocess.run(['git','apply','--no-index',str(P/'source.patch')],cwd=C,check=True)
 need(blob((C/conv).read_bytes())==spec['changed_blob'],'unexpected candidate')
 write(N/'Cargo.toml',(P/'Cargo.toml').read_bytes()); LB=(P/'Cargo.lock').read_bytes();write(N/'Cargo.lock',LB)
 subprocess.run([sys.executable,'-B',str(P/'lift_route.py'),str(D),str(C/conv),str(N/'worker/native/route')],check=True)
 need(H((N/'worker/native/route/core.rs').read_bytes())==spec['lift_sha256'],'generated Core drift')
 write(N/'worker/native/main.rs',(P/'route.rs').read_bytes())
 for f,local in [('resident.rs','main.rs'),('controls.rs','controls.rs'),('meter.rs','meter.rs')]:write(N/'writer/src'/local,(P/f).read_bytes())
 orig=tomllib.loads((D/'Cargo.lock').read_text())['package'];proj=tomllib.loads(LB.decode())['package']
 key=lambda k:(k['name'],k['version']); upstream={key(k):k for k in orig}
 def edge(dep,pkgs):
  bits=dep.split();xs=[key(p) for p in pkgs if p['name']==bits[0] and (len(bits)==1 or bits[1]==p['version'])];need(len(xs)==1,'unresolved dependency '+dep);return xs[0]
 count=0;files=0
 for k in proj:
  if k['name']=='r283-resident-read-proof':need('source' not in k,'root');continue
  q=upstream[key(k)]
  need({edge(t,proj) for t in k.get('dependencies',[])}<={edge(t,orig) for t in q.get('dependencies',[])},'extra upstream dep edge: '+k['name'])
  if 'source' not in k:need('source' not in q and k['name'] in ('proteus-contracts','proteus-session-semantics'),'other local dep');continue
  n='-'.join(key(k));sm=k['checksum'];need(k['source']==q['source']==registry and sm==q['checksum'],'unlocked package '+n)
  arc=next((x/(n+'.crate') for x in a.archives if (x/(n+'.crate')).is_file()),None)
  need(arc is not None,'missing '+n+'.crate');files+=members(arc,n,sm,W/'vendor',a.existing_vendor);count+=1
 need(count==spec['archives'] and files==spec['members'],'archive totals')
 T=a.rust_bin.resolve()
 for n,h in spec['toolchain_sha256'].items():need(H((T/n).read_bytes())==h,'toolchain pin '+n)
 env=dict(PATH=str(T)+':/usr/bin:/bin',HOME=str(W/'home'),CARGO_HOME=str(W/'cargo-home'),CARGO_TARGET_DIR=str(W/'target'),RUSTC=str(T/'rustc'),LC_ALL='C.UTF-8',TMPDIR=str(W/'tmp'))
 cargo=[str(T/'cargo'),'--offline','--locked','--config','source.crates-io.replace-with="proved"','--config','source.proved.directory='+json.dumps(str(W/'vendor'))]
 opts={'default':[],'preserve_order':['--features','preserve_order']}
 for layout,feat in opts.items():
  md=json.loads(subprocess.check_output(cargo+['metadata','--format-version=1',*feat],cwd=N,env=env))
  ids={p['id']:p['name']+'-'+p['version'] for p in md['packages']};rr=md['resolve']
  g={ids[n['id']]:sorted(n['features']) for n in rr['nodes'] if n['id']!=rr['root']}
  need(len(g)==count+2 and H(json.dumps(g,sort_keys=True,separators=(',',':')).encode())==spec['nonroot_all_features_sha256'][layout],'complete feature graph mismatch '+layout)
  need((N/'Cargo.lock').read_bytes()==LB,'rewritten lock')
 receipt=dict(source_files=len(spec['source_files']),archive_count=count,verified_members=files,nonroot_all_features_sha256=spec['nonroot_all_features_sha256'],lift_sha256=spec['lift_sha256'],changed_blob=spec['changed_blob'])
 write(W/'evidence/stage.json',(json.dumps(receipt,indent=2)+'\n').encode());print(json.dumps(receipt),flush=True)
 if a.action=='stage':return
 for layout,feat in opts.items():
  with (W/'evidence'/(layout+'.build.jsonl')).open('w') as log:
   subprocess.run(cargo+['build','--release','--bins','-j',str(a.jobs),'--message-format=json-render-diagnostics',*feat],check=True,cwd=N,env=env,stdout=log)
  for name in ['route','resident']:
   exe=W/'artifacts'/(name+'-'+layout);shutil.copy2(W/'target/release'/name,exe)
   if a.action=='run':
    with (W/'evidence'/(name+'-'+layout+'.jsonl')).open('w') as log:
     subprocess.run([str(exe)],check=True,cwd=N,env=env,stdout=log)
    raw=W/'evidence'/(name+'-'+layout+'.jsonl')
    cf='check_route.py' if name=='route' else 'check_layout.py'
    report=json.loads(subprocess.check_output([sys.executable,'-B',str(P/cf),str(raw)]))
    if name=='resident':need(report['layout']==layout,'layout label')
    write(W/'evidence'/(name+'-'+layout+'-check.json'),(json.dumps(report,indent=2)+'\n').encode())
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--core',type=Path,required=True);p.add_argument('--archives',type=Path,nargs='+',required=True)
 p.add_argument('--existing-vendor',type=Path);p.add_argument('--rust-bin',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
 p.add_argument('--action',choices=['stage','build','run'],default='stage');p.add_argument('--jobs',type=int,default=3);main(p.parse_args())
