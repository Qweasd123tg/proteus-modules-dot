"""Pin to ordinary input normalization and prune by stable ID only; no GUI/external calls."""
from pathlib import Path
import re,tempfile,subprocess,sys
root=Path(sys.argv[1]);rustc=sys.argv[2] if len(sys.argv)>2 else 'rustc'
state=(root/'vendor/gpui-base/src/input/base/state.rs').read_text()
fields=(root/'src/ui/extensions/declarative/fields.rs').read_text()
a=state.index("    pub(super) fn normalize_input<'a>");normal=state[a:state.index('\n    }',a)+6].replace('pub(super) fn','fn')
insert=re.search(r'Node::Input \{ id, .. \} => \{\s*(ids.insert\(\(0, id.clone\(\)\)\);)',fields)[1]
keep=re.search(r'self.fields\s*.inputs\s*(.retain\(\|id, _\| ids.contains\(&\(0, id.clone\(\)\)\)\);)',fields)[1]
program="""use std::{borrow::Cow,collections::{HashMap,HashSet},rc::Rc};
enum MaskPattern{Text,Number{}} fn normalize_number_input(_: &str)->Cow<'_,str>{unreachable!()}
struct State { mask_pattern:MaskPattern, line:bool } impl State{fn is_single_line(&self)->bool{self.line} @@NORMAL@@ }
fn retain(map:&mut HashMap<String,Rc<String>>,widgets:&[&str]){let mut ids=HashSet::new();for s in widgets{let id=s.to_string(); @@INSERT@@ }map@@KEEP@@}
fn main(){let line=State{line:true,mask_pattern:MaskPattern::Text};let area=State{line:false,mask_pattern:MaskPattern::Text};
for draft in ["A\\nB","A\\rB","A\\r\\nB","AB"]{assert_eq!(area.normalize_input(draft),draft);assert_eq!(line.normalize_input(draft),"AB");}
let mut fields=HashMap::new();let old=Rc::new("A\\nB".to_owned());fields.insert("draft".into(),old.clone());retain(&mut fields,&["draft","query"]);assert!(Rc::ptr_eq(&old,&fields["draft"]));retain(&mut fields,&["query"]);assert!(!fields.contains_key("draft"));
println!("Four distinct literal drafts normalize to AB in Line, remain distinct in Area. Both IDs present retains stored draft; search only prunes it. No inspection of physical focus, selection, or actual input events.");}"""
program=program.replace('@@NORMAL@@',normal).replace('@@INSERT@@',insert).replace('@@KEEP@@',keep)
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'r.rs').write_text(program);subprocess.run([rustc,'--edition=2024','-Awarnings',str(p/'r.rs'),'-o',str(p/'r')],check=True);subprocess.run([str(p/'r')],check=True)
