"""Replay the pure row-reconciliation method from two pinned Desktop source trees without running the app."""
import argparse, hashlib, subprocess, tempfile
from pathlib import Path
a=argparse.ArgumentParser(description=__doc__);a.add_argument("base",type=Path);a.add_argument("candidate",type=Path);a.add_argument("--rustc",default="rustc");o=a.parse_args()
root=Path(__file__).resolve().parent; here=Path('src/ui/extensions/declarative')
for name,tree in [('before',o.base),('after',o.candidate)]:
    rows=(tree/here/'rows.rs').read_text()
    fields=(tree/here/'fields.rs').read_text(); lanes=(tree/here/'lanes.rs').read_text(); lst=(tree/here/'list.rs').read_text()
    start=rows.index('    pub fn set_rows('); end=rows.index('    pub fn focus(',start)
    method=rows[start:end]
    arg='rows.clone()' if name=='before' else 'rows'
    for fragment in [f'lanes.set_rows({arg}, cx)',f'list.set_rows({arg}, cx)',f'Lanes::new({arg}, view',f'List::new({arg}, view']: assert fragment in fields,fragment
    real_arg=arg.replace('rows','values')
    cap=lanes[lanes.index('let painted = '):lanes.index(';',lanes.index('let painted = '))+1]
    if name=='after':
        assert 'fn draw(&self, row: &Rc<Row>' in lanes and 'fn draw(&self, row: &Rc<Row>' in lst
        assert 'fn draw(&self, row: &Rc<Self::Row>' in rows
    # Preserve the production capture's receiver type; main injects a borrowed row as at Rows::row.
    argtype='&Record' if name=='before' else '&Rc<Record>'
    src=(root/'frame.rs.in').read_text().replace('//METHOD',method).replace('/*CALL*/',real_arg).replace('/*CAPTURE*/',cap).replace('/*ARG*/',argtype)
    with tempfile.TemporaryDirectory() as t:
        d=Path(t);(d/'harness.rs').write_text(src);subprocess.run([o.rustc,'--edition=2024','-O','--cfg',name,str(d/'harness.rs'),'-o',str(d/'check')],check=True)
        print(name,flush=True);subprocess.run([str(d/'check')],check=True)
