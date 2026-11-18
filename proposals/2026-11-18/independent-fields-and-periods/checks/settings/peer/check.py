"""Independent whitespace, identity and section/field draw matrix. Borrow only the author's GPUI stand-ins."""
import argparse,hashlib,tempfile,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('deps',type=Path);p.add_argument('--rustc',default='rustc');p.add_argument('--candidate',default='after');a=p.parse_args()
hd=Path(__file__).parent
def block(s,n):
 i=s.index('fn '+n+'(');b=s.index('{',i);j=b+1;d=1
 while d:d+=int(s[j]=='{')-int(s[j]=='}');j+=1
 return s[i:j]
stub=(hd.parent/'frame.rs.in').read_text().split('fn main(){')[0]
cat=(a.before/'src/settings/catalog.rs').read_text();schema=(a.before/'src/settings/schema.rs').read_text()
def original(s,n):
 import re
 m=re.search(r'(?m)^ *(?:pub(?:\([^)]*\))? )?fn '+n+r'\s*\(',s);return s[m.start():s.index('fn '+n+'(',m.start())]+block(s,n)
stub=stub.replace('//EDITABLE',original(cat,'editable_field')+'\n'+original(cat,'editable_fields')).replace('//SECTIONS',schema[schema.index('pub struct FieldSection'):schema.index('/// How a text control')].replace('proteus_contracts::domain::ConfigSection','ConfigSection'))
main='''
fn main(){
 let mut ids=0;let mut mis=0;let mut sample=vec![];
 for n in [1,2,3]{for mask in 0..(1<<n){for open in [false,true]{for title in ["","  ","Width","Width ","  Width","Screen"] {for desc in ["","  ","field help","field help  ","Units: points","　"]{
 let fields:Vec<_>=(0..n).map(|i|field(&format!("w{i}"),"Width",mask&(1<<i)!=0,Some(("sec",title,desc)))).collect();
 let rows=draw(&fields,open);let regs=fields.iter().filter(|f|!f.advanced).count();let adv=n-regs;
 let mut direct=vec![];
 for (i,f) in fields.iter().enumerate().filter(|(_,f)|!f.advanced){direct.push(format!("FIELD sample.w{i}: {}",f.title));}
 for (i,f) in fields.iter().enumerate().filter(|(_,f)|f.advanced && (adv==1||open)){direct.push(format!("FIELD sample.w{i}: {}",f.title));}
 assert_eq!(rows.iter().filter(|s|s.starts_with("FIELD ")).cloned().collect::<Vec<_>>(),direct);
 assert_eq!(rows.iter().filter(|s|*s=="TOGGLE").count(),usize::from(adv>1));
 if n==1&&regs==0 {
  let extra=(!title.trim().is_empty()&&title.trim()!="Width")||(!desc.trim().is_empty()&&desc.trim()!="field help");
  let got=rows.iter().any(|s|!s.starts_with("FIELD "));
  if got!=extra {mis+=1;if sample.len()<3{sample.push(format!("title={title:?}, description={desc:?}, rows={rows:?}"));}}
 }
 ids+=1;
 }}}}}
 let paired=[field("screen","Width",true,Some(("screen","Screen","pixels"))),field("print","Width",true,Some(("print","Print","millimeters")))];
 println!("ordered field paths and toggle counts correct for {ids} cases; {mis} singleton distinguishing-text mismatches; e.g. {sample:?}");
 println!("two sections: {:?}",draw(&paired,false));
 if cfg!(candidate){assert_eq!(mis,0)}else{assert!(mis>0)}
}
'''
with tempfile.TemporaryDirectory() as d:
 t=Path(d);baseline=(a.before/'src/ui/settings/group.rs').read_text();assert hashlib.sha256((hd.parents[2]/'patches/advanced-section-header.patch').read_bytes()).hexdigest()=='8e12a36315affd690f11b16bd3d64e936cf01ea828a49d57ec58a4bc00902833'
 for stage in ['base',a.candidate]:
  f=(a.before if stage=='base' else a.after)/'src/ui/settings/group.rs';s=f.read_text();assert block(s,'section_rows')==block(baseline,'section_rows')
  src=t/(stage+'.rs');src.write_text(stub.replace('//METHODS',block(s,'field_rows')+'\n'+block(s,'section_rows'))+ ('\n'+block(s,'adds_context') if 'fn adds_context(' in s else '') +main)
  o=src.with_suffix('');lib=next(a.deps.glob('libserde_json-*.rlib'))
  subprocess.run([a.rustc,'--edition=2024','--cfg','candidate' if stage!='base' else 'baseline','-Awarnings','-L','dependency='+str(a.deps),'--extern','serde_json='+str(lib),src,'-o',o],check=True)
  lines=subprocess.run([o],check=True,capture_output=True,text=True).stdout;assert (('22 singleton' if stage=='base' else '0 singleton') in lines);print(stage+'\n'+lines,flush=True)
