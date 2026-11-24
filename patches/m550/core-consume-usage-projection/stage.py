from pathlib import Path
import tarfile,subprocess,hashlib,json,io,shutil,sys
D=Path(__file__).resolve().parent; S=D.parent;R=S.parents[2]
A=S/'Core-M362-source.tar.gz'
SIDES={
'crates/proteus-session-semantics/src/journal/usage.rs':(
'''    pub fn snapshot(&self, session_id: SessionId) -> SessionUsageSnapshot {''',
'''    /// Finalize a temporary fold without duplicating its requests. Drop any
    /// geometric spare capacity before returning the detached view.
    pub fn into_snapshot(self, session_id: SessionId) -> SessionUsageSnapshot {
        SessionUsageSnapshot {
            session_id,
            revision: self.revision,
            latest_turn_id: self.latest_turn_id,
            requests: self.requests.into_boxed_slice().into_vec(),
        }
    }

    pub fn snapshot(&self, session_id: SessionId) -> SessionUsageSnapshot {'''),
'crates/proteus-core/src/core/session_store/remote/snapshot.rs':(
 '            usage: usage.snapshot(store.session_id()),',
 '            usage: usage.into_snapshot(store.session_id()),')}
def sha(x):return hashlib.sha256(x).hexdigest()
def git(x):return hashlib.sha1(f'blob {len(x)}\0'.encode()+x).hexdigest()
def staged():
 assert sha(A.read_bytes())=='b0d04dabb2d609e72fe690a5c62f2dc3e31e772f9168090253ab5ac8757198a0'
 src={}; inputs={}
 with tarfile.open(A) as t:
  for m in t:
   if m.name.startswith(('crates/proteus-contracts/','crates/proteus-session-semantics/')) or m.name in SIDES.keys() or m.name=='Cargo.lock':
    assert m.isfile() and m.mode in (420,493)
    src[m.name]=(m.mode,t.extractfile(m).read())
 for name,(old,new) in SIDES.items():
  m,b=src[name];a=old.encode();assert b.count(a)==1
  inputs[name]={'old_blob':git(b),'old_bytes':len(b),'new_blob':git(b.replace(a,new.encode()))}
 return src,inputs
if __name__=='__main__':
 src,pins=staged();orig=D/'exact-before';out=D/'m362';orig.mkdir();out.mkdir()
 for p,(mode,b) in src.items():
  f=out/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b);f.chmod(mode)
  if p in SIDES:
   f=orig/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b);f.chmod(mode)
 patch=b''
 for p,(old,new) in SIDES.items():
  f=out/p;b=f.read_bytes().replace(old.encode(),new.encode());f.write_bytes(b)
  cp=subprocess.run(['diff','-U3','--label',f'a/{p}','--label',f'b/{p}',str(orig/p),str(f)],capture_output=True);assert cp.returncode==1
  patch+=f"diff --git a/{p} b/{p}\nindex {pins[p]['old_blob']}..{pins[p]['new_blob']} 100644\n".encode()+cp.stdout
 dst=D/'source.patch';dst.write_bytes(patch)
 for extra in (['--check','--reverse'],['--reverse'],['--check'],[]):
  subprocess.run(['git','apply',*extra,str(dst)],cwd=out,check=True)
 for p,v in pins.items():assert git((out/p).read_bytes())==v['new_blob']
 (D/'source-stage.json').write_text(json.dumps(dict(archive_sha=sha(A.read_bytes()),source_patch_sha=sha(patch),files=pins),indent=2)+'\n')
