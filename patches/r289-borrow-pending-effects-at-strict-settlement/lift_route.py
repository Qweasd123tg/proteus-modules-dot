"""Create full native path crates with an isolated same-map R289 observer."""
import hashlib,json,shutil,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
C='crates/proteus-session-semantics/src/journal/'
FACTS=C+'projection/facts.rs'
PROJECTION=C+'projection.rs'
JOURNAL=C+'mod.rs'
FILES=[FACTS,PROJECTION,JOURNAL,C+'projection/active_ids.rs',C+'projection/sequence.rs',C+'projection/part_identity.rs',C+'history_capture.rs']
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def replace(s,a,b):
 assert s.count(a)==1,a
 return s.replace(a,b,1)
def generate(src,changed,meter,out):
 pins=json.loads((HERE/'route-pins.json').read_text())
 for f in FILES:assert oid((src/f).read_bytes())==pins[f],f
 candidate=changed.read_bytes();assert oid(candidate)==pins['candidate-facts']
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
  if is_candidate:
   s=s[s.index('impl JournalValidationState'):s.index('    fn capture_tool_result(')]+'}\n'
   s=replace(s,'                    let tool_calls = self.tool_calls.clone();','                    let _pending_probe=proof_bridge::begin_pending();\n                    let tool_calls = self.tool_calls.clone();\n                    proof_bridge::after_map_clone();')
   marker='                    for result in pending {\n                        if let Some(index) = self.capture_tool_result(result)? {'
  else:
   s=replace(s,'                    let pending = self\n                        .tool_calls','                    let _pending_probe=proof_bridge::begin_pending();\n                    let pending = self\n                        .tool_calls')
   marker='                    for result in pending {\n                        if let Some(index) = self.capture_tool_result(&result)? {'
  result='result' if is_candidate else '&result'
  s=replace(s,marker,'                    proof_bridge::end_pending_prepare();\n                    for result in pending {\n                        proof_bridge::visit('+result+', self.tool_calls.get(&result.call_id).unwrap().effect.as_ref().unwrap());\n                        let captured=self.capture_tool_result('+result+')?;\n                        proof_bridge::after_capture('+result+', captured.map(|index| &self.history[index]));\n                        if let Some(index) = captured {')
  return s
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
 wr('src/journal/projection.rs',(src/PROJECTION).read_text()+'\npub mod proof_bridge;\n')
 wr('src/journal/mod.rs',(src/JOURNAL).read_text()+'\npub use projection::proof_bridge;\n')
 wr('src/journal/projection/proof_bridge.rs',(HERE/'bridge.rs').read_text())
 (out/'main.rs').write_text((HERE/'route.rs').read_text())
 (out/'meter.rs').write_text(meter.read_text())
if __name__=='__main__':generate(*(Path(p) for p in sys.argv[1:]))
