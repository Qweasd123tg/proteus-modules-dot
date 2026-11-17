"""Compile the pinned pane-size functions against plain, in-memory test splits."""
from pathlib import Path
import subprocess,sys,tempfile
root=Path(sys.argv[1])/'crates/tabs/src'
here=Path(__file__).parent
def fn(p, name):
    src=(root/p).read_text()
    start=src.index(name); index=src.index('{',start); opened=1
    while opened:
        index+=1; opened+=(src[index]=='{')-(src[index]=='}')
    return src[start:index+1]

with tempfile.TemporaryDirectory() as td:
    temp=Path(td); text=(here/'frame.rs').read_text()
    for key, methods in {
        '@@SIZE@@': [('size.rs','pub fn is_fixed('),('size.rs','fn weight(')],
        '@@ROOT@@': [('tree.rs','pub(super) fn min_panes(')],
        '@@GEOMETRY@@': [('geometry.rs','pub fn resize(')],
        '@@FREE@@': [('size.rs','pub(super) fn extents('),('size.rs','pub(super) fn set_extents('),('size.rs','pub(super) fn balance(')],
    }.items():
        text=text.replace(key,'\n'.join(fn(p,n) for p,n in methods))
    (temp/'frame.rs').write_text(text)
    subprocess.run(['rustc','--edition','2024','-O',str(temp/'frame.rs'),'-o',str(temp/'probe')],check=True)
    subprocess.run([str(temp/'probe'),*sys.argv[2:]],check=True)
