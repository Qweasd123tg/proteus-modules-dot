from pathlib import Path
import argparse,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('before',type=Path);p.add_argument('after',type=Path);p.add_argument('--rustc',default='rustc');o=p.parse_args()
def number(tree):
 path=tree/'src/ui/extensions/declarative/render.rs' if tree.is_dir() else tree
 text=path.read_text();start=text.index('fn number(value: f64)');end=text.index('\n}',start)+2
 assert text.count('number(bar.value)')==1
 return text[start:end]
with tempfile.TemporaryDirectory() as td:
 t=Path(td);s=Path(__file__).with_name('peer.rs.in').read_text().replace('/*BEFORE*/',number(o.before)).replace('/*AFTER*/',number(o.after))
 (t/'probe.rs').write_text(s);subprocess.run([o.rustc,'--edition=2024',t/'probe.rs','-o',t/'check'],check=True);subprocess.run([t/'check'],check=True)
