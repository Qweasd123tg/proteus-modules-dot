"""Create full native path crates with an isolated same-map R289 observer."""
import hashlib,json,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
C='crates/proteus-session-semantics/src/journal/'
FACTS=C+'projection/facts.rs'
ACTIVE=C+'projection/active_ids.rs'
FIX='crates/proteus-core/examples/session_index_fixture.rs'
PROJECTION=C+'projection.rs'
JOURNAL=C+'mod.rs'
FILES=[FACTS,PROJECTION,JOURNAL,ACTIVE,FIX,C+'projection/sequence.rs',C+'projection/part_identity.rs',C+'history_capture.rs']
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def replace(s,a,b):
 assert s.count(a)==1,a
 return s.replace(a,b,1)
def generate(src,changed,changed_active,meter,out):
 pins=json.loads((HERE/'route-pins.json').read_text())
 for f in FILES:assert oid((src/f).read_bytes())==pins[f],f
 candidate=changed.read_bytes();assert oid(candidate)==pins['candidate-facts']
 active=changed_active.read_bytes();assert oid(active)==pins['candidate-active']
 def cr(name):
  d=out/'crates'/name;donor=src/'crates'/name
  if d.is_symlink():
   assert name=='proteus-contracts'
   for p in donor.rglob('*'):
    if p.is_file():assert (d/p.relative_to(donor)).read_bytes()==p.read_bytes(),p
  else:
   shutil.copytree(donor,d,dirs_exist_ok=True)
  return d
 contracts=cr('proteus-contracts')
 sem=cr('proteus-session-semantics')
 def wr(f,data):p=sem/f;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(data)
 def facts(s,is_candidate):
  s=replace(s,'    pub fn apply(&mut self, record: &JournalRecord) -> Result<()> {',f"    fn {'apply_instrumented_candidate' if is_candidate else 'apply_instrumented_stock'}(&mut self, record: &JournalRecord) -> Result<()> {{")
  if is_candidate:s=s[s.index('impl JournalValidationState'):s.index('    fn capture_tool_result(')]+'}\n'
  old='self.check_captured_active_ids(index)?;' if is_candidate else 'self.check_active_ids(None)?;'
  assert s.count(old)==2
  return s.replace(old,'self.observe_captured_active_ids(index, '+str(is_candidate).lower()+')?;')
 stock=(src/FACTS).read_text()
 wr('src/journal/projection/facts.rs',facts(stock,False)+'\n'+facts(candidate.decode(),True)+'''
impl JournalValidationState {
    pub fn apply(&mut self, record: &JournalRecord) -> Result<()> {
        if proof_bridge::is_candidate(){
            self.apply_instrumented_candidate(record)
        }else{
            self.apply_instrumented_stock(record)
        }
    }
}
''')
 typed=active.decode()
 typed=replace(typed,'            ids.messages.insert(message.id);','            proof_bridge::active_fast();\n            ids.messages.insert(message.id);')
 typed=replace(typed,'        for message in messages {','        for message in messages {\n            proof_bridge::scan_row();')
 typed=replace(typed,'            for part in &message.parts {','            for part in &message.parts {\n                proof_bridge::scan_part();')
 wr('src/journal/projection/active_ids.rs',typed+(HERE/'active-probe.rs').read_text())
 wr('src/journal/projection.rs',(src/PROJECTION).read_text()+'\npub mod proof_bridge;\n')
 wr('src/journal/mod.rs',(src/JOURNAL).read_text()+'\npub use projection::proof_bridge;\n')
 wr('src/journal/projection/proof_bridge.rs',(HERE/'bridge.rs').read_text())
 seed=(src/FIX).read_text().split('    let messages: Vec<_> = (0..rows)',1)[1].split('    let thread_id = new_thread_id();',1)[0]
 (out/'main.rs').write_text((HERE/'route.rs').read_text()+'\nfn public_rows(rows:usize,repeats:usize)->Vec<CanonicalMessage>{\n    let messages: Vec<_> = (0..rows)'+seed+'messages\n}\n')
 (out/'meter.rs').write_text(meter.read_text())
 (out/'edge.rs').write_text(meter.with_name('edge.rs').read_text())
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
