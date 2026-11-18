"""Source-linked projection for tiny-tally's three ordinary widgets. No SDK host / UI app."""
from pathlib import Path
import hashlib,json,sys,tempfile,subprocess,time
r=Path(__file__).resolve().parents[1]
ext,desk=map(Path,sys.argv[1:3])
def lines(p,b):
 data=p.read_bytes(); assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==b,p
 return data.decode().splitlines(keepends=True)
def cut(a,start,end):return ''.join(a[start-1:end])
ui=lines(ext/'sdk/src/ui.rs','0bdfb9723583c0e23bab0ffedbbae90a42e25876')
w=lines(desk/'src/declarative/widget.rs','67e6b2ac8ad06f43ddab7afffbc3e7c2adc00eb3')
with tempfile.TemporaryDirectory() as t:
 d=Path(t);(d/'src').mkdir()
 (d/'Cargo.toml').write_text('[package]\nname="tiny-tally-shapes"\nversion="0.1.0"\nedition="2024"\n[dependencies]\nserde={version="1",features=["derive"]}\nserde_json="1"\nanyhow="1"\n')
 s='#![allow(dead_code)]\nuse serde::Deserialize; use anyhow::{Result,bail}; use serde_json::json;\n'
 s+='mod upstream_builders {\n'+cut(ui,5,32)+cut(ui,71,73)+cut(ui,145,147)+'}\n'
 s+='#[path='+json.dumps(str(r/'tiny-tally/src/tally.rs'))+']mod tally;\n'
 s+=cut(w,27,29)+cut(w,270,287)+cut(w,303,306)+'}\n'+cut(w,393,398)+cut(w,418,448)+cut(w,450,457)
 s+='fn check(n:&Node)->Result<()> { let kids:&[Node]=match n{ Node::Card{children,..}=>children, Node::Text{..}=>&[],\n'+cut(w,744,753)+'}; for c in kids{check(c)?} Ok(())}\n'
 s+='''fn main(){
 use upstream_builders::{card,text,table};
 let cases=[("Paper: 3\\nInk: 2\\nPaper: 4",card(Some("Total: 9"),vec![table(&["Item","Count"],vec![vec!["Paper".into(),"7".into()],vec!["Ink".into(),"2".into()]])])),
 (" \x20",text("No counts yet. Try Paper: 3")),("Salt: fine: 2",text("Line 1: use one non-negative whole count after the colon")),("Paper: 2\\nInk: many",text("Line 2: use one non-negative whole count after the colon")),("東京: 3\\nTea: 0",card(Some("Total: 3"),vec![table(&["Item","Count"],vec![vec!["東京".into(),"3".into()],vec!["Tea".into(),"0".into()]])]))];
 for (src,want) in cases { let node=tally::render(src); assert_eq!(node,want); let read:Node=serde_json::from_value(node).unwrap();check(&read).unwrap(); }
 // Deliberately malformed check fixtures (not defects found in the app).
 let bad=json!({"type":"table","columns":["A","B"],"rows":[["a"]]});assert!(check(&serde_json::from_value(bad).unwrap()).is_err());
 assert!(serde_json::from_value::<Node>(json!({"type":"table","columns":["A"],"rows":[[3]]})).is_err());
 println!("5/5 rendered fixtures equal actual SDK constructors and decode using the pinned Card, Text and Table serde arms; table widths valid. 2/2 deliberately invalid fixtures (wrong width or number-valued cell) rejected.");
}'''
 (d/'src/main.rs').write_text(s);g=time.perf_counter()
 subprocess.run(['cargo','build','--offline','--quiet','--manifest-path',str(d/'Cargo.toml'),'--target-dir',str(d/'build')],check=True)
 print('Source projection cargo build seconds:',round(time.perf_counter()-g,6),flush=True)
 g=time.perf_counter();subprocess.run([str(d/'build/debug/tiny-tally-shapes')],check=True)
 print('Source projection fixture process seconds:',round(time.perf_counter()-g,6))
