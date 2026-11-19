import sys,json,os,subprocess
from pathlib import Path
root=Path(os.environ['RUN_ROOT']).resolve()
cache=Path(os.environ['CARGO_RELEASE_CACHE']).resolve()
fingerprint=cache/'.fingerprint'; dll=cache/'deps'
side=sys.argv[1]; mode=sys.argv[2]; out=root/side
subdirs={'lib':'session-storage-91cebcbf7edd783f/lib-session_storage','worker':'proteus-session-storage-module-b03b4ceb52413b20/bin-proteus-session-storage-module','test':'session-storage-8ef0dbe891cfa18b/test-lib-session_storage'}
spec=fingerprint/(subdirs['worker' if mode=='integration' else mode]+'.json')
data=json.loads(spec.read_text()); args=[str(Path(os.environ['RUST_1_95'])/'bin/rustc'),'--edition=2024','-C','opt-level=3','-C','link-arg=-fuse-ld=lld','-L','dependency='+str(dll)]
for d in (cache/'build').glob('*/out'):
    if any(d.glob('*.a')): args+=['-L','native='+str(d)]
if mode=='integration': data['deps'] += [x for x in json.loads((fingerprint/(subdirs['test']+'.json')).read_text())['deps'] if x[1]=='tempfile']
for _,name,_,sig in data['deps']:
    if mode=='integration' and name not in ('tempfile','proteus_contracts','serde_json'): continue
    sig=sig.to_bytes(8,'little').hex(); matches=[v for v in fingerprint.glob(f'*/lib-{name}') if v.read_text()==sig]; assert len(matches)==1,(name,sig,matches)
    loc=dll/('lib'+name+'-'+matches[0].parent.name.rsplit('-',1)[1]+'.rlib')
    if mode=='worker' and name=='session_storage':loc=out/'libsession_storage.rlib'
    assert loc.is_file(),loc
    args+=['--extern',f'{name}={loc}']
if mode=='integration':
    os.environ['CARGO_BIN_EXE_proteus-session-storage-module']=str(out/'worker'); args+=['--test','--crate-name','process','src/components/session-storage-module/tests/process.rs','-o',out/'itest']
elif mode=='worker': args+=['--crate-name','proteus_session_storage_module','src/components/session-storage-module/src/main.rs','-o',out/'worker']
elif mode=='lib': args+=['--crate-name','session_storage','--crate-type=rlib','src/storage/session-storage/src/lib.rs','-o',out/'libsession_storage.rlib']
else: args+=['--test','--crate-name','session_storage','src/storage/session-storage/src/lib.rs','-o',out/'unit-tests']
os.environ.update(PATH=str(Path(os.environ['RUST_1_95'])/'lib/rustlib/x86_64-unknown-linux-gnu/bin/gcc-ld')+':'+os.environ['PATH'],CARGO_PKG_NAME='proteus-session-storage-module',CARGO_PKG_VERSION='0.1.0-alpha.3',TMPDIR=str(root))
args=[v.replace("src/", side+"/", 1) if isinstance(v,str) and v.startswith("src/") else v for v in args]
subprocess.run(args,check=True,cwd=root)
