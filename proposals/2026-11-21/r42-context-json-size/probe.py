"""Use one coherent Cargo debug/deps cache for both implementations; no checkout changes."""
import subprocess as sp
import sys
import tempfile
from pathlib import Path

base = '32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f'
repo, deps = (Path(arg).resolve() for arg in sys.argv[1:])
here = Path(__file__).resolve().parent
src = Path('crates/proteus-core/src/core/session_store')
summary = src / 'context_summary.rs'
counter = src / 'json_size.rs'
test_alloc = Path('crates/proteus-contracts/src/test_alloc.rs')

def source(p):
    return sp.check_output(['git','-C',repo,'show',f'{base}:{p}'])

def put(dest, data):
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(data)

with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    sp.run(['git','init','-q'], cwd=d, check=True)
    for p in [src.with_suffix('.rs'), summary, src/'remote/view/cache.rs', src/'remote/view/cache/pages.rs']:
        put(d/p, source(p))
    sp.run(['git','apply','--check',here/'source.patch'],cwd=d,check=True)
    sp.run(['git','apply','--whitespace=error',here/'source.patch'],cwd=d,check=True)
    for dest, data in [('baseline.rs',source(summary)), ('candidate.rs',(d/summary).read_bytes()),
                       ('json_size.rs',(d/counter).read_bytes()),('test_alloc.rs',source(test_alloc)),
                       ('probe.rs',(here/'probe.rs').read_bytes())]:
        put(d/dest,data)
    cmd = ['rustc','--edition=2024','--test','-Copt-level=2','-Cdebuginfo=0','-Cstrip=symbols',
           '-Clink-arg=-fuse-ld=lld','-L',f'dependency={deps}']
    for name in ['serde','serde_json','proteus_contracts']:
        choices = list(deps.glob(f'lib{name}-*.rlib'))
        if len(choices) != 1:
            raise ValueError((name,choices))
        cmd.extend(['--extern',f'{name}={choices[0]}'])
    sp.run(cmd+['probe.rs','-o','probe'],cwd=d,check=True)
    sp.run([d/'probe','--nocapture','--test-threads=1'],cwd=d,check=True)
