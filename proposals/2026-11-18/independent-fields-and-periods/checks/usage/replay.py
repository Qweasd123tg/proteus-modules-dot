"""Compile only actual in-memory selector / row placement methods and exercise them on benign synthetic data."""
from pathlib import Path
import argparse,itertools,json,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('deps',type=Path);p.add_argument('--rustc',default='rustc');p.add_argument('--fragments',action='store_true');a=p.parse_args()
def block(s,marker):
    i=s.index(marker);b=s.index('{',i);d=1;j=b+1
    while d:d+=int(s[j]=='{')-int(s[j]=='}');j+=1
    return s[i:j]
def sources(root):
    if a.fragments:
        return ((root/'report.frag').read_text(),(root/'tests.frag').read_text(),(a.before/'model-key.frag').read_text(),(a.before/'entry.frag').read_text(),(a.before/'value.rs').read_text())
    s=root/'packages/usage/src';r=(s/'report.rs').read_text();return r,(s/'tests.rs').read_text(),r,(s/'entry.rs').read_text(),(root/'sdk/src/value.rs').read_text()
def lib(n):
    fs=list(a.deps.glob('lib'+n+'-*.rlib'));assert len(fs)==1,fs
    return str(fs[0])
base=sources(a.before);change=sources(a.after)
reg='#[test]\n'+block(change[1],'fn latest_period_excludes_requests_outside_any_turn(')
place=base[3][base[3].index('let turn = request.str("turn_id");'):base[3].index('    let marker')]
def build(root,temp,stage):
    r,t,m,e,v=sources(root)
    code='pub use serde_json::{Value,json};mod sdkvalue{'+v+'}\nuse sdkvalue::ValueExt; mod report {use super::*;\n'+block(m,'pub fn model_key(')+'\n'+block(r,'pub fn turn_ids(')+'\n'+block(r,'pub fn scoped<')+'\n}\n'+block(t,'fn ids(')+'\n'+reg+'\n'
    code+='fn place(request:&Value,turns:&[String])->String{'+place+'\nplace}\n'
    code+='''
fn main(){
 use std::io::{self,BufRead};
 for l in io::stdin().lock().lines(){
  let f:Value=serde_json::from_str(&l.unwrap()).unwrap();let snap=&f["snapshot"];
  let rows=report::scoped(snap,f.str("period"),f.opt_str("model"));
  let turns=report::turn_ids(snap);
  let places:Vec<_>=rows.iter().map(|row|place(row,&turns)).collect();
  println!("{}",json!({"ids":ids(&rows),"places":places,"items":rows.len()}));
 }
}'''
    o=temp/stage;src=o.with_suffix('.rs');src.write_text(code)
    cmd=[a.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(a.deps),'--extern','serde_json='+lib('serde_json'),src]
    subprocess.run(cmd+['-o',o],check=True);test=temp/(stage+'_test')
    subprocess.run(cmd+['--test','-o',test],check=True)
    res=subprocess.run([test],capture_output=True,text=True)
    assert bool(res.returncode)==(stage=='before'),res.stdout
    print(stage+': upstream-ready native regression '+('RED (expected)' if res.returncode else 'GREEN'))
    return o
missing=object()
fixtures=[]; oracle=[]
for turns in [[],[None],[missing],[''],['a'],[None,'a'],[missing,None,'b','a','b'],['a','b',None,'b','a',''],['b',None,'a','b','b']]:
 for latest,period,model in itertools.product([missing,None,'','a','b','absent'],['all','latest','a','b','absent'],[None,'fixture/x','fixture/y','fixture/z']):
  rows=[]
  for j,t in enumerate(turns):
   row={"exchange_id":f"r{j}","model":{"provider":"fixture","model":"xy"[j%2]}}
   if t is not missing:row['turn_id']=t
   rows.append(row)
  snap={"requests":rows}
  if latest is not missing:snap["latest_turn_id"]=latest
  fixtures.append({"snapshot":snap,"period":period,"model":model})
  ranked=list(dict.fromkeys(t for t in turns if isinstance(t,str) and t))
  want=[r for r in rows if (not model or model=='fixture/'+r['model']['model']) and (period=='all' or (isinstance(r.get('turn_id'),str) and r['turn_id'] and r['turn_id']==(latest if period=='latest' else period)))]
  oracle.append(dict(ids=[r['exchange_id'] for r in want],places=[f"Ход {ranked.index(r['turn_id'])+1}" if r.get('turn_id') in ranked else "Вне хода" for r in want],items=len(want)))
doc=''.join(json.dumps(x)+'\n' for x in fixtures)
with tempfile.TemporaryDirectory() as td:
 for stage,root in [('before',a.before),('after',a.after)]:
  o=build(root,Path(td),stage); res=subprocess.run([o],input=doc,text=True,capture_output=True,check=True)
  out=list(map(json.loads,res.stdout.splitlines()));assert len(out)==len(oracle)
  wrong=[i for i,(v,expect) in enumerate(zip(out,oracle)) if v!=expect]
  if stage=='before':
   assert wrong
   for i in wrong:
    f=fixtures[i];assert f['period']=='latest' and not f['snapshot'].get('latest_turn_id') and out[i]['items'] and set(out[i]['places'])=={'Вне хода'}
  else:assert not wrong
  print(f'{stage}: {len(wrong)}/{len(oracle)} mismatches; named/current/all subsets compare exact ids, source order, period counts and row placement labels')
