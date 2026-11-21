#!/usr/bin/env python3
"""Reproduce allocator counts via instrumented test-only Core startup on both variants."""
from pathlib import Path
import argparse,os,re,shutil,subprocess,tempfile
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('stock',type=Path,help='exact local checkout/verified archive Core 32e56ecb')
ap.add_argument('target',type=Path,help='existing Cargo target; use no additional broad build cache')
ap.add_argument('output',type=Path,help='new directory for logs')
a=ap.parse_args()
here=Path(__file__).resolve().parent
a.output=a.output.resolve()
a.output.mkdir(exist_ok=False)
env={**os.environ,'CARGO_TARGET_DIR':str(a.target.resolve()),'CARGO_INCREMENTAL':'0',
     'CARGO_BUILD_JOBS':'1','CARGO_PROFILE_TEST_DEBUG':'0','RUST_TEST_THREADS':'1'}
assert all(Path(env[k]).is_file() for k in ('PROTEUS_TEST_REFERENCE_MODULE','PROTEUS_TEST_SESSION_STORAGE_MODULE'))
src=Path('crates/proteus-core/src')
prefix='startup::'
def suite(root,kind,server):
    f=root/src/'app_server.rs'
    f.write_text(server)
    log=a.output/(kind+'.log')
    with log.open("w") as out:
        subprocess.run(['cargo','test','--locked','--offline','-p','proteus-core','--lib',prefix,
                        '--','--nocapture','--test-threads=1'], env=env,cwd=root,stdout=out,stderr=subprocess.STDOUT,check=True)
    result=log.read_text()
    cases={}
    for m in re.finditer(r'r52 config (\w+) site=(\w+) calls=(\d+) bytes=(\d+)',result):
        case,site,calls,bs=m.groups()
        cases.setdefault(case,{})[site]=(int(calls),int(bs))
    assert len(cases)==8,result[-3000:]
    print(kind,next(l for l in result.splitlines() if l.startswith('test result:')),flush=True)
    return cases
def hook(s,old,raw):
    assert s.count(old)==1,old
    return s.replace(old,raw)
with tempfile.TemporaryDirectory(prefix='r52-startup-exact-') as d:
    root=Path(d)/'Core'
    shutil.copytree(a.stock.resolve(),root,symlinks=True,ignore=shutil.ignore_patterns('.git','target'))
    f=root/src/'app_server.rs'
    old=f.read_text()
    subprocess.run(['git','apply','--check',here/'source.patch'],cwd=root,check=True)
    subprocess.run(['git','apply',here/'source.patch'],cwd=root,check=True)
    candidate=f.read_text()
    (root/src/'app_server/startup').mkdir(exist_ok=True)
    shutil.copyfile(here/'measure.rs',root/src/'app_server/startup/r52_measure.rs')
    shutil.copyfile(root/'crates/proteus-contracts/src/test_alloc.rs',root/src/'r52_test_alloc.rs')
    with (root/src/'app_server/startup.rs').open('a') as h:
        h.write('\n#[cfg(test)]\npub(super) mod r52_measure;\n')
    with (root/src/'lib.rs').open('a') as h:
        h.write('\n#[cfg(test)]\nmod r52_test_alloc;\n')
    old=hook(old,'let selection_config = config.clone();','let selection_config = startup::r52_measure::copy_config(&config, "selection");')
    old=hook(old,'let config_snapshot = Arc::new(RwLock::new(config.clone()));','let config_snapshot = Arc::new(RwLock::new(startup::r52_measure::copy_config(&config, "config_snapshot")));')
    candidate=hook(candidate,'let mut builder = AgentRuntime::builder(config.clone(), cwd)','let mut builder = AgentRuntime::builder(startup::r52_measure::copy_config(&config, "builder"), cwd)')
    first=suite(root,'stock',old)
    second=suite(root,'candidate',candidate)
    assert set(first)==set(second)
    for k, before in first.items():
        assert set(before)=={'selection','config_snapshot'}
        after=second[k]
        assert set(after)=={'builder'} and before['selection']==before['config_snapshot']==after['builder']
        calls,bs=after['builder']
        print(f'{k}: launch clones 2 → 1; allocation requests {2*calls} → {calls}; bytes {2*bs} → {bs}',flush=True)
