#!/usr/bin/env python3
"""Replay from exact upstream. Requires git, tar, stable Rust with rustfmt and Cargo.lock dependencies."""
import hashlib
import os
from pathlib import Path
import statistics
import subprocess as sp
import sys
import tempfile

BASE = '892f627570369ed60d7205eb0d351c753ec4305f'
HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve()
PATCH = HERE/'source.patch'
def run(*args, **kwargs):
    return sp.run(args, check=True, **kwargs)

with tempfile.TemporaryDirectory(prefix='r44-analysis-preview-') as name:
    root = Path(name)
    src = root/'src'
    src.mkdir()
    env = dict(os.environ, CARGO_TARGET_DIR=str(root/'target'), CARGO_INCREMENTAL='0', TZ='UTC')
    with (root/'base.tar').open('wb') as output:
        run('git','-C',REPO,'archive',BASE,stdout=output)
    run('tar','xf',root/'base.tar','-C',src)
    os.chdir(src)
    run('git','init','-q')
    run('git','add','packages/analysis/src')
    run('git','apply','--index','--check',PATCH)
    main = Path('packages/analysis/src/main.rs')
    original = main.read_text()
    assert original.count('fn main() {') == 1
    for arm in ('stock','candidate'):
        if arm=='candidate':
            run('git','apply','--whitespace=error',PATCH)
            run('git','diff','--check')
            run('git','apply','--reverse','--check',PATCH)
            run('rustfmt','--check','--edition','2024','packages/analysis/src/text.rs','packages/analysis/src/tests.rs')
        run('cargo','test','--release','--locked','-p','extension-analysis',env=env)
        main.write_text(original.replace('fn main() {','#[allow(dead_code)]\nfn extension_main() {')+'\n'+(HERE/'probe.rs').read_text())
        run('cargo','build','--release','--locked','-p','extension-analysis',env=env)
        import shutil
        shutil.copy2(root/'target/release/analysis',root/arm)
        main.write_text(original)
    def output(arm,command):
        return sp.check_output([root/arm,command],env=env)
    wire=output('stock','wire')
    assert wire==output('candidate','wire'), 'projection differs'
    print('wire: identical; length',len(wire),'sha256',hashlib.sha256(wire).hexdigest(),flush=True)
    vals={}
    for rep in range(7):
        for arm in (('candidate','stock') if rep%2 else ('stock','candidate')):
            for row in output(arm,'bench').decode().splitlines():
                case,*fields=row.split()
                vals.setdefault((case,arm),[]).append(list(map(int,fields)))
    print('case arm input_B preview_alloc_B preview_calls card_alloc_B card_calls preview_ns card_ns (median of seven)')
    for (case,arm), rows in vals.items():
        # Memory is deterministic for this pure projection; record raw timings too.
        assert all(r[:5]==rows[0][:5] for r in rows)
        print(case,arm,*map(statistics.median,zip(*rows)))
        print('  raw_ns',[(r[-2],r[-1]) for r in rows])
