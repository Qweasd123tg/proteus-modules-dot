#!/usr/bin/env python3
"""Replay with git, tar, rustfmt and stable cargo. Use CARGO_NET_OFFLINE=true with cached lock deps."""
import hashlib
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile

BASE = '892f627570369ed60d7205eb0d351c753ec4305f'
HERE = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve()

def call(*args, **kw):
    return subprocess.run(args, check=True, **kw)

with tempfile.TemporaryDirectory(prefix='usage-turn-index-') as temp:
    work = Path(temp)
    src = work / 'src'
    src.mkdir()
    archive = work / 'input.tar'
    with archive.open('wb') as f:
        call('git', '-C', REPO, 'archive', BASE, stdout=f)
    call('tar', '-xf', archive, '-C', src)
    os.chdir(src)
    os.environ['TZ'] = 'UTC'
    # A fresh target prevents stale binaries from another source tree with older Git archive mtimes.
    target = work / 'target'
    os.environ['CARGO_TARGET_DIR'] = str(target)
    call('git', 'init', '-q')
    call('git', 'add', 'packages/usage/src')
    patch = HERE / 'source.patch'
    call('git', 'apply', '--index', '--check', patch)
    main = Path('packages/usage/src/main.rs')
    original = main.read_text()
    assert original.count('fn main() {') == 1
    benches = {}
    for arm in ('stock', 'candidate'):
        if arm == 'candidate':
            call('git', 'apply', patch)
            call('git', 'diff', '--check')
            call('git', 'apply', '--reverse', '--check', patch)
            call('rustfmt', '--edition', '2024', '--check', 'packages/usage/src/main.rs')
        call('cargo', 'test', '--locked', '-p', 'extension-usage')
        main.write_text(original.replace('fn main() {', '#[allow(dead_code)]\nfn extension_main() {') + '\n' + (HERE/'probe.rs').read_text())
        call('cargo', 'build', '--release', '--locked', '-p', 'extension-usage')
        benches[arm] = work / arm
        shutil.copy2(target/'release/usage', benches[arm])
        main.write_text(original)
    results = [subprocess.check_output([binary, 'wire']) for binary in benches.values()]
    assert results[0] == results[1], 'projection bytes differ'
    print('wire: identical; bytes', len(results[0]), 'sha256', hashlib.sha256(results[0]).hexdigest(), flush=True)
    obs = {}
    for i in range(8):
        for arm in (('stock','candidate') if i % 2 == 0 else ('candidate','stock')):
            for line in subprocess.check_output([benches[arm]], text=True).splitlines():
                n,u,idx,view = map(int,line.split())
                obs.setdefault((n,u,arm), []).append((idx, view))
    for (n,u,arm), vals in obs.items():
        print('samples_ns', n, u, arm, vals)
    print('requests unique index_median_us(stock→candidate) view_median_us(stock→candidate)')
    for n,u in dict.fromkeys((n,u) for n,u,a in obs):
        def med(k, arm):
            return statistics.median(x[k] for x in obs[n,u,arm])/1000
        print(n, u, *(f'{med(k,"stock"):.2f}→{med(k,"candidate"):.2f}' for k in (0,1)))
