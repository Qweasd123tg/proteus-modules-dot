"""Compile exact spans bodies in a bounded rendering-bookkeeping fixture."""
import pathlib,subprocess,sys,tempfile
P=pathlib.Path
if len(sys.argv)!=3: raise SystemExit("python3 run.py BASE_DESKTOP PATCHED_DESKTOP (rustc in PATH)")
def extract(s,needle,indent):
    i=s.index(' '*indent+needle); end=s.index('\n'+' '*indent+'}',i)+2+indent
    return s[i:end]
files=[(P(x)/'src/ui/extensions/declarative/tree.rs').read_text() for x in sys.argv[1:]]
t=P(__file__).with_name('frame.rs').read_text().replace('/*KEY*/',extract(files[0],'fn fold_key(',4)).replace('/*CHILDREN*/',extract(files[0],'fn children(',0))
for src,token,name in zip(files,['/*BASE*/','/*AFTER*/'],['before_spans','after_spans']):
    t=t.replace(token,extract(src,'fn spans(',4).replace('fn spans(',f'fn {name}(',1))
with tempfile.TemporaryDirectory() as tmp:
    f=P(tmp)/'frame.rs'; b=P(tmp)/'check'; f.write_text(t)
    subprocess.run(['rustc','--edition','2024','-O','-D','warnings',str(f),'-o',str(b)],check=True);subprocess.run([str(b)],check=True)
