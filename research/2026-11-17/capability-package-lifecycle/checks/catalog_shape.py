"""Read-only catalog wire-shape experiment; no package, artifact, command, or application is opened."""
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse, copy, hashlib, json, subprocess

p=argparse.ArgumentParser(description=__doc__)
for name in ('desktop','modules','extensions','deps'):p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--rustc',default='rustc')
p.add_argument('--serde',type=Path);p.add_argument('--serde-json',type=Path)
a=p.parse_args()
def rlib(stem, override):
    if override: return override.resolve(strict=True)
    fs=list(a.deps.glob('lib'+stem+'-*.rlib'));assert len(fs)==1,(stem,len(fs));return fs[0].resolve()
def section(s,first,end):
    i=s.index(first);return s[i:s.index(end,i+len(first))]
base=a.desktop/'src/catalog/schema.rs'
def blob(path):
    data=path.read_bytes()
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
if blob(base)!='c48176a739706e44ba468cf3a2de5086e1a517ec':
    raise SystemExit('The Desktop schema does not match the pinned revision.')
src=base.read_text()
# Derive-only: do not include the filesystem, package, source build or install functions.
parts=(section(src,'#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]','impl Kind {')
       +section(src,'#[derive(Clone, Debug, Deserialize)]','impl SourcePackage {')
       +section(src,'#[derive(Deserialize)]\n#[serde(deny_unknown_fields)]\nstruct Index', '#[derive(Clone)]\npub struct Catalog'))
assert not any(w in parts for w in ['std::fs','impl SourcePackage','pub fn read','Command::'])
driver=Path(__file__).with_name('catalog_probe.rs').read_text()
docs=[('Modules',a.modules/'proteus-catalog.json'),('Extensions',a.extensions/'proteus-catalog.json'),('Desktop/mixed-example',a.desktop/'examples/catalog/proteus-catalog.json')]
seeds=[]
def case(label,index,valid_index,expected):seeds.append({'label':label,'index':index,'valid_index':valid_index,'expected':expected})
for label,path in docs:
    doc=json.loads(path.read_text());case(label,doc,True,[True]*len(doc['entries']))
mix=json.loads(docs[-1][1].read_text())
base_module=next(x for x in json.loads(docs[0][1].read_text())['entries'] if x['id']=='memory-pack')
base_panel=next(x for x in json.loads(docs[1][1].read_text())['entries'] if x['id']=='plan')
def composed(entries):
    return {'format':1,'title':'catalog shape only','categories':[{'id':'example','title':'Example'}],'entries':[dict(x,category='example') for x in entries]}
case('One index can list one backend entry beside a client entry',composed([base_module,base_panel]),True,[True,True])
family={'id':'sample-feature','kind':'bundle','version':'1.0','title':'Sample','path':'feature','members':['memory-pack','sample-ui']}
case('Composite package kind is not an Entry; sibling survives',composed([family,base_panel]),True,[False,True])
case('Members on a known module kind are not accepted',composed([dict(base_module,members=['sample-ui']),base_panel]),True,[False,True])
case('Requires on a known client kind is not accepted',composed([base_module,dict(base_panel,requires=['memory-pack'])]),True,[True,False])
case('Additional top-level features list is not accepted',dict(composed([base_module,base_panel]),features=[family]),False,[])
# requirements is a list of human-readable strings in the source record, not a typed dependency edge.
w=copy.deepcopy(base_module);w['source']['requirements']=['Rust','sample-ui']
case('Source requirements are parsed even if they contain an arbitrary name',composed([w]),True,[True])
cases='\n'.join(json.dumps(x,ensure_ascii=False) for x in seeds)+'\n'
with TemporaryDirectory() as tmp:
    d=Path(tmp); f=d/'check.rs';f.write_text(driver.replace('//DECLARATIONS',parts))
    subprocess.run([a.rustc,'--edition=2024','-Awarnings',str(f),'-L','dependency='+str(a.deps.resolve()),'--extern','serde='+str(rlib('serde',a.serde)),'--extern','serde_json='+str(rlib('serde_json',a.serde_json)),'-o',str(d/'check')],check=True)
    subprocess.run([str(d/'check')],input=cases,text=True,check=True)
