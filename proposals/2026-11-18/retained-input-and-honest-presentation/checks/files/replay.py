"""Build the in-memory tree module from a supplied checkout. No Cargo, host or filesystem-listing callback."""
import argparse, pathlib, shutil, subprocess
p=argparse.ArgumentParser()
p.add_argument('source',type=pathlib.Path, help='Root of Extensions checkout')
p.add_argument('out',type=pathlib.Path)
p.add_argument('rustc'); p.add_argument('deps',type=pathlib.Path,help='Directory with prebuilt serde_json and anyhow .rlib')
p.add_argument('--observe',action='store_true',help='Also count actual production queue-child path.clone evaluations / frontier size')
a=p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
tree=a.source/'packages/files/src'
s=(tree/'tree.rs').read_text()
if a.observe:
    target='.map(|entry| (entry.path.clone(), depth + 1)),'
    assert s.count(target)==1
    s=s.replace(target,'.map(|entry| { crate::bump(); (entry.path.clone(), depth + 1) }),')
    target='fn expand_all('; h,t=s.split(target)
    point='                );\n            }\n        }\n    }\n'
    assert t.count(point)==1
    t=t.replace(point,point.replace('                );','                );\n                crate::observe(queue.len());'))
    s=h+target+t
(a.out/'tree.rs').write_text(s)
for src in [tree/'paths.rs',tree/'tree_tests.rs',a.source/'sdk/src/value.rs',pathlib.Path(__file__).with_name('model.rs')]:
    shutil.copyfile(src,a.out/src.name)
def rlib(n):
    fs=sorted(a.deps.glob('lib'+n+'-*.rlib'))
    assert len(fs)==1,fs
    return str(fs[0])
common=[a.rustc,'--edition=2024','-Awarnings','-C','debuginfo=0','-L','dependency='+str(a.deps),'--extern','serde_json='+rlib('serde_json'),'--extern','anyhow='+rlib('anyhow'),str(a.out/'model.rs')]
for suffix,options in [('native',['--test']),('probe',[])]:
    subprocess.run(common+options+['-o',str(a.out/suffix)],check=True)
