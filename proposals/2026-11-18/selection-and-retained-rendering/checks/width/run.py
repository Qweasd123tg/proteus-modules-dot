"""Compare C.UTF-8 display widths for five ordinary names using only two pure Core formatters."""
from pathlib import Path
import argparse, subprocess, tempfile, sys
a=argparse.ArgumentParser(description=__doc__);a.add_argument('core',type=Path);a.add_argument('--rustc',default='rustc');o=a.parse_args();here=Path(__file__).parent.resolve()
def read(path,sha):
    spec='c2cbadee518788f306ffb2b5271036b2658ea8cc:crates/proteus-core/src/'+path
    assert subprocess.check_output(['git','-C',o.core,'rev-parse',spec],text=True).strip()==sha
    return subprocess.check_output(['git','-C',o.core,'show',spec],text=True)
def piece(text,name):
    at=text.index(name);return text[at:text.index('\n}\n',at)+2]+'\n'
head=read('main/repl_render.rs','7aa118218065149a68c61da2a0b8e6fc70ae5989');table=read('main.rs','409b8f2e4399eb58fd1329d5d2b2d717981ea313')
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp); (p/'width.rs').write_bytes((here/'width.rs').read_bytes());(p/'frame-source.rs').write_text(piece(head,'pub(super) fn small_block'))
    (p/'table-source.rs').write_text(piece(table,'fn render_table<const')+'\n'+piece(table,'fn render_table_row<const'))
    subprocess.run([o.rustc,'--edition=2024',p/'width.rs','-o',p/'probe'],check=True)
    (p/'width-output.txt').write_bytes(subprocess.check_output([p/'probe']))
    subprocess.run([sys.executable,here/'check_width.py'],cwd=p,check=True)
