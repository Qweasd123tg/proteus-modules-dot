#!/usr/bin/env python3
"""Compile the actual old comparator and new production ordering helper together."""
from pathlib import Path
import argparse,hashlib,re,shutil,subprocess,tempfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('stock',type=Path);p.add_argument('deps',type=Path);p.add_argument('fixtures',type=Path)
a=p.parse_args(); here=Path(__file__).resolve().parent
rel='crates/proteus-core/src/core/session_store/remote/prepared.rs'
base=a.stock.resolve()/rel
old=base.read_text();needle='    candidates.sort_by(|left, right| {'
assert old.count(needle)==1
i=old.index(needle);j=old.index('    });',i)+len('    });')
with tempfile.TemporaryDirectory(prefix='r53-start-order-') as td:
    d=Path(td);file=d/rel;file.parent.mkdir(parents=True)
    shutil.copy2(base,file)
    subprocess.run(['git','apply',str(here/'source.patch')],check=True,cwd=d)
    new=file.read_text();k=new.index('fn order_startup_candidates(');e=new.index('\npub(crate) fn prepare_latest_workspace_session',k)
    (d/'observed.rs').write_text('fn old_order(candidates: &mut [StorageSessionDescriptor]) {\n'+old[i:j]+'\n}\n'+new[k:e])
    for name in ['measure.rs','alloc.rs']:
        shutil.copy2(here/name,d/name)
    dep=a.deps.resolve()
    args=['rustc','--edition','2024','-C','opt-level=3','-L',f'dependency={dep}']
    for name in ['proteus_contracts','serde_json']:
        lib,=dep.glob(f'lib{name}-*.rlib')
        args.extend(['--extern',f'{name}={lib}'])
    subprocess.run(args+['measure.rs','-o','measure'],cwd=d,check=True)
    subprocess.run([str(d/'measure'),str(a.fixtures.resolve())],cwd=d,check=True)
