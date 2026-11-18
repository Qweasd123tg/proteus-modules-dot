from pathlib import Path
import sys, subprocess, tempfile
roots=[Path(s) for s in sys.argv[1:3]];lib=Path(sys.argv[3]).resolve();rust=sys.argv[4]
for s,tree in zip(['base','after'],roots):
 d=(tree/'src/settings/draft.rs').read_text()
 e=(tree/'src/ui/settings/editors.rs').read_text()
 def extract(src,sig):
  i=src.index(sig); j=src.index('{',i); dep=1
  while dep>0:
   j+=1;dep+=(src[j]=='{')-(src[j]=='}')
  return src[i:j+1]
 meth=['pub fn set_value(','pub fn module_config(']+(['pub fn reset_value('] if s=='after' else [])
 m='\n'.join(extract(d,x) for x in meth)
 helpers='\n'.join(extract(d,x) for x in ['fn ensure_object(','fn remove_nested(','fn is_empty_object('])
 before='self.update_draft(cx, |draft| draft.set_value(path, None));';after='self.draft.reset_value(path, &self.baseline);'
 arm=extract(e,'pub(super) fn reset_field(');assert(before if s=='base' else after) in arm
 p=Path(__file__).with_name('fixture.rs').read_text().replace('/* METHODS */',m).replace('/* HELPERS */',helpers).replace('/* RESET */','let _=b;d.set_value(p,None)' if s=='base' else 'd.reset_value(p,b)')
 with tempfile.TemporaryDirectory() as td:
  t=Path(td);src=t/'peer.rs';b=t/'peer';src.write_text(p);subprocess.run([rust,'--edition=2024','-Awarnings','--cfg',s,src,'--extern','serde_json='+str(lib),'-L','dependency='+str(lib.parent),'-o',b],check=True)
  result=subprocess.run([b],capture_output=True,text=True);print(s,result.stdout.strip(),flush=True);assert result.stdout==Path(__file__).with_name(s+'.log').read_text(),result.stdout
