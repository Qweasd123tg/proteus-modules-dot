"""Confirm that the large modeled row count is valid in the pinned public Sortable schema."""
from pathlib import Path
import argparse,subprocess as sp,tempfile
p=argparse.ArgumentParser();p.add_argument('desktop',type=Path);p.add_argument('deps',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args();rev='2307e9c67125bbe66f15ced51317a2dfcc437aa4'
with tempfile.TemporaryDirectory() as t:
 d=Path(t)
 for name in ['widget','graph','lanes','list','tree','control']:
  (d/(name+'.rs')).write_bytes(sp.check_output(['git','-C',a.desktop,'show',rev+':src/declarative/'+name+'.rs']))
 spec='''use serde_json::json;
mod widget;mod graph;mod lanes;mod list;mod tree;mod control;
mod diff{pub type FileInfo=serde_json::Value;}mod icons{pub fn lucide(_:&str)->Option<()>{unreachable!()}}
mod svg{pub fn validate(_:&str)->anyhow::Result<()>{unreachable!()}}
fn verify(count:usize)->bool{let rows=(0..count).map(|i|json!({"id":format!("field:項目:{i}"),"label":format!("Field {i}")})).collect::<Vec<_>>();let data=json!({"type":"sortable","id":"priorities","items":rows,"action":"reorder"});serde_json::from_value::<widget::Node>(data).unwrap().validate().is_ok()}
fn main(){for n in [0,16,256,1024,4096,4999]{assert!(verify(n));}assert!(!verify(5000));println!("Public Sortable schema accepted 4096 rows and 4999 rows; root + 5000 rows correctly rejected.");}'''
 f=d/'schema.rs';f.write_text(spec);cmd=[a.rustc,'--edition=2024','-Awarnings',f,'-o',d/'gate','-L','dependency='+str(a.deps)]
 for n in ['serde','serde_json','anyhow']:lib,=a.deps.glob('lib'+n+'-*.rlib');cmd+=['--extern',n+'='+str(lib)]
 sp.run(cmd,check=True);sp.run([d/'gate'],check=True)
