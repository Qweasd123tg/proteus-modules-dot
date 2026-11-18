"""Replay offline against pinned Git objects in temporary trees. No user workspace or application is opened."""
from pathlib import Path
import argparse, hashlib, shutil, subprocess, sys, tempfile
p=argparse.ArgumentParser(description=__doc__)
for n in ('desktop','extensions','deps'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--rustc',default='rustc');p.add_argument('--node',default='node');a=p.parse_args()
root=Path(__file__).resolve().parent.parent;ck=root/'checks';deps=a.deps.resolve();ds='2307e9c67125bbe66f15ced51317a2dfcc437aa4';es='ef064381d2194d95faef2b85f6cc3a1c34c6b975'
for line in (root/'SHA256SUMS').read_text().splitlines():
    sha,name=line.split('  ',1);assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,name
def run(*args,expected=0,out=None,cwd=None):
    proc=subprocess.run(args,stdout=out,cwd=cwd)
    if proc.returncode!=expected:raise RuntimeError((args,proc.returncode,expected))
def py(file,*args):run(sys.executable,ck/file,*args)
def lib(name):
    options=list(deps.glob('lib'+name+'-*.rlib'));assert len(options)==1,(name,options);return options[0]
patches=sorted((root/'patches').glob('*.patch'))
targets={s[6:] for f in patches for s in f.read_text().splitlines() if s.startswith('--- a/')}
sources=targets|{'src/ui/extensions/declarative/render.rs','src/declarative/widget.rs','vendor/gpui-fast/src/window.rs','vendor/gpui-fast/src/elements/div.rs','crates/diff/src/parse.rs','packages/files/src/paths.rs','packages/files/src/tree_tests.rs','sdk/src/value.rs'}
with tempfile.TemporaryDirectory() as td:
    work=Path(td);base=work/'before';cand=work/'after'
    for n in sources:
        repo,ref=(a.extensions,es) if n.startswith(('packages/','sdk/')) else (a.desktop,ds)
        dest=base/n;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(subprocess.check_output(['git','-C',repo,'show',ref+':'+n]))
    shutil.copytree(base,cand)
    for f in patches:
        run('git','apply','--check','--whitespace=error',f,cwd=cand);run('git','apply','--whitespace=error',f,cwd=cand)
    undo=work/'undo';shutil.copytree(cand,undo)
    for f in reversed(patches):run('git','apply','--reverse','--whitespace=error',f,cwd=undo)
    assert all((undo/s).read_bytes()==(base/s).read_bytes() for s in sources)
    print(f'{len(patches)} patches applied; restored {len(targets)} edited pinned blobs byte-for-byte.',flush=True)
    py('bindings/replay.py',base,cand,'--serde-json',lib('serde_json'),'--rustc',a.rustc)
    for area,fix in [('number','number-exact-whole'),('tag','tag-literal-value')]:
        py(area+'/replay.py','--desktop',a.desktop,'--patch',root/('patches/'+fix+'.patch'),'--serde-json',lib('serde_json'),'--rustc',a.rustc)
    py('settings_peer.py',base,cand,lib('serde_json'),a.rustc)
    py('files/peer.py',base/'packages/files/src',cand/'packages/files/src','--rustc',a.rustc)
    py('picker/check.py',base,cand,'--rustc',a.rustc);py('picker/peer.py',work,a.rustc)
    red=work/'diff-test-only-red';shutil.copytree(base/'crates/diff/src',red)
    shutil.copyfile(cand/'crates/diff/src/tests.rs',red/'tests.rs')
    run(a.rustc,'--edition=2024','--test',red/'lib.rs','--extern','serde='+str(lib('serde')),'-L','dependency='+str(deps),'-o',red/'tests')
    proc=subprocess.run([red/'tests'],capture_output=True,text=True)
    assert proc.returncode!=0 and '8 passed; 1 failed' in proc.stdout and 'metadata_without_a_patch_does_not_claim_to_know_the_contents' in proc.stdout
    print('New diff regression case fails on baseline as expected (8 passed, 1 failed).',flush=True)
    for nm,tree in [('before',base),('after',cand)]:
        w=work/('diff-'+nm);w.mkdir();code=tree/'crates/diff/src/lib.rs'; common=[a.rustc,'--edition=2024','-L','dependency='+str(deps)]
        libopts=['--crate-name','proteus_diff','--extern','serde='+str(lib('serde')),code]; rlib=w/'libproteus_diff.rlib'
        run(*common,*libopts,'--test','-o',w/'tests');run(w/'tests');run(*common,*libopts,'--crate-type','rlib','-o',rlib)
        for x in ['check','peer']:
            run(*common,'--cfg','baseline' if nm=='before' else 'candidate',ck/('diff/'+x+'.rs'),'--extern','proteus_diff='+str(rlib),'-o',w/x)
            run(w/x,expected=(1 if x=='check' and nm=='before' else 0))
        for watch in [False,True]:
            fw=work/('files-'+nm+str(watch))
            py('files/replay.py',tree,fw,a.rustc,deps,*(['--observe'] if watch else []))
            run(fw/'native');log=fw/'probe.jsonl'
            with log.open('w') as out:run(fw/'probe',out=out)
    paths=[work/('files-'+nm+str(observe))/'probe.jsonl' for observe in [True,False] for nm in ['before','after']]
    run(a.node,ck/'files/check.mjs',*paths)
print('All focused checks completed; no GUI, host, provider or actual project directory.')
