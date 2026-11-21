"""Reproduce against the pinned checkout with compiled Core deps and a JSONL worker.
python3 probe.py CORE TARGET/debug/deps /path/to/proteus-session-storage-module
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import os, subprocess, sys
here=Path(__file__).resolve().parent
repo,deps,worker=map(lambda p:Path(p).resolve(),sys.argv[1:])
base='32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f'
path=Path('crates/proteus-core/src/app_server/http/analysis.rs')
def source(path):
    return subprocess.check_output(['git','-C',repo,'show',f'{base}:{path}'], text=True)
def function(src,start):
    i=src.index(start)
    return src[i:src.index('\n}',i)+2]
with TemporaryDirectory() as temp:
    w=Path(temp)
    p=w/path
    p.parent.mkdir(parents=True)
    old=source(path)
    p.write_text(old)
    subprocess.run(['git','init','-q'],cwd=w,check=True)
    subprocess.run(['git','apply','--check',here/'source.patch'],cwd=w,check=True)
    subprocess.run(['git','apply','--whitespace=error',here/'source.patch'],cwd=w,check=True)
    new=p.read_text()
    # The HTTP route/state machinery is outside the tested boundary. Include the exact
    # cold read, query helpers, fixture factory and upstream analysis test unchanged.
    prefix='use super::*;\n'
    sess=source(path.with_name('sessions.rs'))
    for f in ['pub(super) fn required_session_query(', 'pub(super) fn percent_decode_query_value(', 'fn hex_value(']:
        prefix+=function(sess,f)+'\n'
    (w/'support.rs').write_text(source('crates/proteus-core/tests/support/model.rs'))
    for label,src,call in [('stock',old,'project(s, &p, r)'),('candidate',new,'project(s, p.records, r)')]:
        mod=w/label
        mod.mkdir()
        (mod/'mod.rs').write_text(prefix+src[src.index('fn parse('):] + '''
        pub(super) fn run(s: SessionId, p: JournalProjection, r: Option<TurnId>) -> Result<AppSessionAnalysis> { ''' + call+' }\n')
        (mod/'tests.rs').write_text(source(path.with_suffix('')/'tests.rs'))
    (w/'main.rs').write_bytes((here/'probe.rs').read_bytes())
    cmd=['rustc','--edition=2024','--test','-Copt-level=1','-Cstrip=symbols','-Clink-arg=-fuse-ld=lld',
         '-L',f'dependency={deps}', str(w/'main.rs'),'-o',str(w/'probe')]
    for name in ['anyhow','serde_json','proteus_contracts','proteus_core','proteus_session_semantics','tempfile','tokio','toml','async_trait']:
        ext='so' if name=='async_trait' else 'rlib'
        files=list(deps.glob(f'lib{name}-*.{ext}'))
        assert len(files)==1,(name,files)
        cmd+=['--extern',f'{name}={files[0]}']
    subprocess.run(cmd,check=True)
    subprocess.run([str(w/'probe'),'--test-threads=1','--nocapture'],cwd=w,check=True,
                   env={**os.environ,'PROTEUS_TEST_SESSION_STORAGE_MODULE':str(worker)})
