#!/usr/bin/env python3
"""Compile only the pinned public enum/validation branches used by the fixtures.
Usage: python3 schema.py DESKTOP_ROOT RUSTC RUST_DEP_DIR. DEP_DIR must contain one
compatible prebuilt each of serde(with derive), serde_json, anyhow. No Cargo/build.rs.
Optionally pass a .git object directory instead of a checkout (reads the pinned commit)."""
import pathlib,subprocess,sys,tempfile
from pathlib import Path
root,rustc,libs=map(Path,sys.argv[1:4]); here=Path(__file__).resolve().parent
def source(name):
    p='src/declarative/'+name+'.rs'
    return ((root/p).read_text() if (root/'src').exists() else subprocess.check_output(['git','--git-dir='+str(root),'show','2307e9c:'+p],text=True))
def lines(t,a,b):return ''.join(t.splitlines(True)[a-1:b])
w=source('widget'); prefix=w.split('pub enum Node {')[0]; start=prefix.rsplit('#[derive',1)[1]
schema=lines(w,9,14)+'#[derive'+start+'pub enum Node {\n'+lines(w,42,71)+lines(w,320,324)+'}\n'
schema+=lines(w,393,398)+lines(w,418,448)+lines(w,518,524)+lines(w,530,537)
schema+='impl Node {\n'+lines(w,574,587)+lines(w,655,671)+lines(w,713,713).replace('| Node::Fill','Node::Fill')+lines(w,790,807)+lines(w,828,834)
with tempfile.TemporaryDirectory() as td:
    td=Path(td); stub='mod icons { pub fn lucide(_: &str)->Option<()> { panic!("fixture contains no icons") } }\n'
    for name in ['control','graph','tree','lanes','list']:
        (td/(name+'.rs')).write_text(source(name).split('#[cfg(test)]')[0])
    (td/'widget.rs').write_text(schema)
    root_test=(here/'roots.rs.in').read_text()
    if len(sys.argv)>4:
        from integration import build
        root_test=root_test[:root_test.index('fn main(){')]+build(root, Path(sys.argv[4]), here)
    (td/'main.rs').write_text('#![allow(dead_code,unused_imports)]\n'+stub+'mod control;mod graph;mod tree;mod lanes;mod list;mod widget;\n'+root_test)
    args=[str(rustc),'--edition=2024','-L','dependency='+str(libs), str(td/'main.rs'),'-o',str(td/'run')]
    for name in ['serde','serde_json','anyhow']:
        dep,=libs.glob('lib'+name+'-*.rlib'); args+=['--extern',name+'='+str(dep)]
    subprocess.run(args,check=True);sys.exit(subprocess.run([str(td/'run')]).returncode)
