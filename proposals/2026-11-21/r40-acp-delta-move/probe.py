"""Compare both ACP projectors without changing the caller's checkout.
Usage: python3 probe.py /path/to/Proteus-core /path/to/target/debug/deps
"""
from pathlib import Path
import subprocess, sys, tempfile

here = Path(__file__).resolve().parent
repo, deps = (Path(arg).resolve() for arg in sys.argv[1:])
base = '32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f'
path = Path('crates/proteus-core/src/app_server/acp')
file = path / 'projection.rs'


def source(file):
    return subprocess.check_output(['git', '-C', repo, 'show', f'{base}:{file}'], text=True)


def item(src, head):
    start = src.index(head)
    return src[start:src.index('\n}', start) + 2]


with tempfile.TemporaryDirectory() as temp:
    w = Path(temp)
    p = w / file
    p.parent.mkdir(parents=True)
    p.write_text(source(file))
    subprocess.run(['git', 'init', '-q'], cwd=w, check=True)
    subprocess.run(['git', 'apply', '--check', here / 'source.patch'], cwd=w, check=True)
    subprocess.run(['git', 'apply', '--whitespace=error', here / 'source.patch'], cwd=w, check=True)
    for name, src in [('stock', source(file)), ('candidate', p.read_text())]:
        m = w / name
        m.mkdir()
        (m / 'projection.rs').write_text(src)
        (m / 'tool_updates.rs').write_text(source(path / 'tool_updates.rs'))
        (m / 'mod.rs').write_text('''use super::*;
use agent_client_protocol::Error;
mod projection;
mod tool_updates;
''' + item(source(path / 'mod.rs'), 'fn internal(') + '''
pub(super) fn fresh(session: SessionId) -> impl Side { projection::Projection::new(session) }
impl Side for projection::Projection {
    fn run(&mut self, e: EventEnvelope) -> Output { self.event(e) }
    fn fallback(&self) -> Option<SessionUpdate> { self.fallback_output("fallback".into()) }
    fn settle(&mut self) -> Vec<SessionUpdate> { self.settle_tools() }
}
''' + '\n'.join('#[test]\n' + item(source(path/'tests.rs'), 'fn ' + f + '(') for f in [
                'successful_plan_metadata_becomes_an_acp_plan_without_invented_progress',
                'canonical_completion_does_not_repeat_streamed_unicode_or_peer_text',
                'readable_reasoning_uses_thought_chunks_without_duplicate_completion_or_answer_state']))
    (w / 'main.rs').write_bytes((here / 'probe.rs').read_bytes())
    cmd = ['rustc', '--edition=2024', '--test', '-Copt-level=1', '-Cstrip=symbols',
           '-Clink-arg=-fuse-ld=lld', '-L', f'dependency={deps}']
    for lib in ['proteus_contracts', 'agent_client_protocol', 'serde_json', 'tokio']:
        files = list(deps.glob(f'lib{lib}-*.rlib'))
        assert len(files) == 1, (lib, files)
        cmd += ['--extern', f'{lib}={files[0]}']
    subprocess.run(cmd + ['main.rs', '-o', 'probe'], cwd=w, check=True)
    subprocess.run(['./probe', '--test-threads=1', '--nocapture'], cwd=w, check=True)
