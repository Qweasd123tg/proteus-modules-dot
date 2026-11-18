#!/usr/bin/env python3
"""Validate pinned sources, apply/reverse the proposals and run isolated checks.
No installation, access to a user profile, modification of a checkout or network.
"""
import argparse,hashlib,shutil,subprocess,sys,tempfile
from pathlib import Path
a=argparse.ArgumentParser(description=__doc__)
for arg in ('desktop','extensions','core','serde-json','markdown-rlib'):
    a.add_argument('--'+arg,required=True,type=Path)
a.add_argument('--rustc',default='rustc');a.add_argument('--node',default='node')
o=a.parse_args();root=Path(__file__).resolve().parent.parent;ck=root/'checks'; patches=sorted((root/'patches').glob('*.patch'))
dc='2307e9c67125bbe66f15ced51317a2dfcc437aa4';ec='ef064381d2194d95faef2b85f6cc3a1c34c6b975'
def run(*args,cwd=None):
    subprocess.run(args,cwd=cwd,check=True)
def py(sub,*args):
    run(sys.executable,ck/sub,*args)
for line in (root/'SHA256SUMS').read_text().splitlines():
    digest,path=line.split('  ',1); assert hashlib.sha256((root/path).read_bytes()).hexdigest()==digest,path
files={n[6:] for p in patches for n in p.read_text().splitlines() if n.startswith('--- a/')}
with tempfile.TemporaryDirectory() as work:
    t=Path(work); raw=t/'raw'; adapted=t/'adapted'; sv='packages/mermaid-render/svg-theme.mjs'
    for f in files:
        src,ref=(o.extensions,ec) if f==sv else (o.desktop,dc)
        data=subprocess.check_output(['git','-C',src,'show',ref+':'+f])
        (raw/f).parent.mkdir(exist_ok=True,parents=True);(raw/f).write_bytes(data)
    shutil.copytree(raw,adapted)
    for p in patches:
        run('git','apply','--check','--whitespace=error',p,cwd=adapted);run('git','apply','--whitespace=error',p,cwd=adapted)
    undo=t/'undo';shutil.copytree(adapted,undo)
    for p in reversed(patches):run('git','apply','--reverse','--whitespace=error',p,cwd=undo)
    assert all((raw/f).read_bytes()==(undo/f).read_bytes() for f in files)
    print(f'{len(patches)} proposals applied; {len(files)} pinned source blobs restored byte-for-byte.',flush=True)
    py('projects/check.py',raw,adapted,'--rustc',o.rustc)
    py('checkbox/replay.py','--desktop',o.desktop,'--serde-json',o.serde_json,'--patch',root/'patches/checkbox-restore.patch','--rustc',o.rustc)
    # Match the independently reviewed helper before compiling its oracle.
    peer=(ck/'checkbox/peer.rs').read_text()
    helper=peer[peer.index('fn checkbox_value('):peer.index('\nfn arrays(')].strip()
    assert helper in (adapted/'src/ui/settings/fields.rs').read_text()
    run(o.rustc,'--edition=2024',ck/'checkbox/peer.rs','-L','dependency='+str(o.serde_json.resolve().parent),'--extern','serde_json='+str(o.serde_json.resolve()),'-o',t/'checkbox-peer')
    run(t/'checkbox-peer')
    py('rows/run.py',raw,adapted,'--rustc',o.rustc);py('rows/peer.py',adapted,'--rustc',o.rustc)
    for f in ('check','peer'):run(o.node,ck/('svg/'+f+'.mjs'),raw/sv,adapted/sv)
    run(o.node,ck/'svg/isolation.mjs',adapted/sv)
    py('width/run.py',o.core,'--rustc',o.rustc)
    py('references/probe.py',o.desktop,o.markdown_rlib,'--rustc',o.rustc)
    lib=o.markdown_rlib.resolve()
    run(o.rustc,'--edition=2024',ck/'references/source-label-probe.rs','--extern','markdown='+str(lib),'-L','dependency='+str(lib.parent),'-o',t/'source-label')
    run(t/'source-label')
print('All four candidate checks and two baseline diagnostics completed. No Desktop, running REPL, renderer or clipboard.')
