"""Run the real Git history unit tests on both implementations without editing the checkout.
Usage: python3 probe.py /path/to/Proteus-core /path/to/target/debug/deps
Dependencies: rustc 1.95, git, and one coherent set of built Core dependencies.
"""
from pathlib import Path
import os
import subprocess as sp
import sys
import tempfile

repo, deps = (Path(arg).resolve() for arg in sys.argv[1:])
packet = Path(__file__).resolve().parent
pin = '32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f'
http = Path('crates/proteus-core/src/app_server/http')
log = http / 'workspace/git/log.rs'
history = http / 'tests/workspace_git_history.rs'
doc = Path('docs/guides/runtime-and-events.md')
def src(p):
    return sp.check_output(['git', '-C', repo, 'show', f'{pin}:{p}'])

def put(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)

with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
    sp.run(['git', 'init', '-q'], cwd=tmp, check=True)
    for p in [log, history, doc]:
        put(tmp / p, src(p))
    for flags in [['--check'], ['--whitespace=error']]:
        sp.run(['git','apply', *flags, packet/'source.patch'], cwd=tmp, check=True)
    candidate = (tmp / log).read_bytes()
    # Use complete production Git modules (including the bounded process launcher), not a reimplementation.
    paths = sp.check_output(['git','-C', repo, 'ls-tree','--name-only','-r', pin,'--',
                            http/'workspace/git', http/'workspace/git.rs'], text=True).splitlines()
    for p in map(Path, paths):
        put(tmp / p, src(p))
    constants = [l for l in src(http/'workspace.rs').decode().splitlines() if l.startswith('const MAX_')]
    (tmp / http / 'workspace.rs').write_text('\n'.join(constants) + '\npub(super) mod git;\n')
    fixture = src(http / 'tests/workspace_fixture.rs').split(b'pub(super) async fn post(')[0]
    put(tmp / http/'tests/workspace_fixture.rs', fixture)
    # Additional control: explicit detached HEAD may be reachable from no named ref.
    put(tmp / http/'tests.rs', b'''use serde_json::{json, Value};
mod workspace_fixture;
mod workspace_git_history;
#[test]
fn detached_commit_remains_in_all_refs_log() {
    use workspace_fixture::{git, init, json};
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path();
    init(root);
    git(root, &["commit", "--allow-empty", "-qm", "branch"]);
    git(root, &["switch", "-q", "--detach"]);
    git(root, &["commit", "--allow-empty", "-qm", "detached only"]);
    let result = json(super::workspace::git::log(root, super::workspace::git::LogQuery {
        limit: 5, skip: 0, all: true,
    }).unwrap());
    assert_eq!(result["entries"].as_array().unwrap().len(), 2);
    assert_eq!(result["entries"][0]["summary"], "detached only");
    assert_eq!(result["entries"][0]["hash"], result["head"]);
}
''')
    put(tmp / http/'probe.rs', b'#![allow(unused_imports, dead_code)]\nmod workspace;\nmod tests;\n')
    args = ['rustc','--edition=2024','--test','-Copt-level=1','-Cstrip=symbols',
            '-Clink-arg=-fuse-ld=lld','-L',f'dependency={deps}']
    for lib in ['serde','serde_json','tempfile','anyhow','libc','proteus_contracts']:
        matches = list(deps.glob(f'lib{lib}-*.rlib'))
        assert len(matches) == 1, (lib, matches)
        args += ['--extern', f'{lib}={matches[0]}']
    regression = 'tests::workspace_git_history::workspace_git_log_all_refs_without_a_current_commit'
    for name, data in [('baseline',src(log)), ('candidate',candidate)]:
        print(f'=== {name} ===', flush=True)
        put(tmp / log,data)
        sp.run(args + [str(tmp/http/'probe.rs'),'-o',str(tmp/'probe')], cwd=tmp, check=True)
        command = [str(tmp/'probe'), '--test-threads=1']
        result = sp.run(command, cwd=tmp, env=env, stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
        print(result.stdout, flush=True)
        if name == 'baseline':
            assert (result.returncode == 101 and '5 passed; 1 failed;' in result.stdout
                    and f'{regression} ... FAILED' in result.stdout
                    and 'left: Null' in result.stdout and 'right: "latest"' in result.stdout)
        else:
            assert result.returncode == 0 and '6 passed; 0 failed;' in result.stdout
