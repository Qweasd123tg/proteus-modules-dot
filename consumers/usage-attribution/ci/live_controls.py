#!/usr/bin/env python3
"""Hosted Linux controls of ready fixtures, not general descendant settlement."""
import importlib.util
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys

spec = importlib.util.spec_from_file_location('envelope', Path(__file__).with_name('envelope.py'))
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class InjectWaitFailure:
    """Real child; only the supervisor's wait syscall adapter is fault-injected."""
    def __init__(self, process): self.process = process
    def __getattr__(self, name): return getattr(self.process, name)
    def wait(self, timeout): raise subprocess.TimeoutExpired('injected wait seam', timeout)


def run(root):
    root.mkdir()
    results = []
    old_limit = e.MAX_PIPE
    e.MAX_PIPE = 4096
    try:
        for case in ('success', 'nonzero', 'timeout', 'output_cap', 'inherited_pipe', 'injected_wait_failure'):
            leaf = root / case; leaf.mkdir(); child_artifacts = leaf / 'child'; child_artifacts.mkdir()
            read_fd, write_fd = os.pipe()
            process = None
            try:
                process = subprocess.Popen([sys.executable, '-B', '-I', str(Path(__file__).with_name('live_fixture.py')), case, str(write_fd)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, pass_fds=(write_fd,))
                os.close(write_fd); write_fd = None
                with selectors.DefaultSelector() as selector:
                    selector.register(read_fd, selectors.EVENT_READ)
                    if not selector.select(3): raise RuntimeError('fixture readiness deadline')
                    if os.read(read_fd, 64) != b'ready\n': raise RuntimeError('fixture readiness mismatch')
                if os.getpgid(process.pid) != process.pid: raise RuntimeError('fixture group identity')
                wrapper = InjectWaitFailure(process) if case == 'injected_wait_failure' else process
                receipt = e.supervise(wrapper, child_artifacts, leaf, .5)
                expected = {'success': None, 'nonzero': 'failed_command', 'timeout': 'stopped_deadline',
                            'output_cap': 'stopped_pipe_limit', 'inherited_pipe': 'stopped_deadline',
                            'injected_wait_failure': 'stopped_deadline'}[case]
                if receipt['reason'] != expected: raise RuntimeError('unexpected control result: ' + case)
                if receipt['status'] != ('passed' if case == 'success' else 'failed'): raise RuntimeError('control status')
                if receipt['elapsed_seconds'] > 7: raise RuntimeError('control exceeded bounded window')
                if case == 'injected_wait_failure':
                    if receipt['cleanup']['direct_child'] != 'unproven': raise RuntimeError('injected wait failure hidden')
                    # Separately reconcile the exact still-owned child; this is not a claim
                    # that a real kernel-level unkillable process has been exercised.
                    process.wait(timeout=2)
                    receipt['injected_wait_reconciled'] = True
                elif case in ('timeout', 'output_cap', 'inherited_pipe'):
                    if receipt['cleanup']['direct_child'] != 'reaped': raise RuntimeError('direct fixture not reaped')
                if case == 'success' and (leaf/'stdout.bin').read_bytes() != b'fixture-ok\n': raise RuntimeError('success bytes')
                if case == 'nonzero' and receipt['returncode'] != 23: raise RuntimeError('nonzero exit')
                if case == 'output_cap' and receipt['captured_bytes']['stdout'] != 4096: raise RuntimeError('cap mismatch')
                receipt['case'] = case
                receipt['fixture_identity'] = {'pid': process.pid, 'pgid': process.pid, 'ready': True}
                e.save(leaf/'result.json', receipt)
                results.append(receipt)
            finally:
                os.close(read_fd)
                if write_fd is not None: os.close(write_fd)
                if process is not None and process.returncode is None:
                    e.stop(process)
                    if process.returncode is None: raise RuntimeError('fixture direct child reconciliation failed; retire job')
    finally:
        e.MAX_PIPE = old_limit
    report = {'status': 'passed', 'cases': [r['case'] for r in results], 'count': 6,
              'scope': 'ready fixed Python fixtures; 4 KiB pipe cap; 0.5-second clock',
              'injected_wait_failure': 'real child with injected wait adapter failure; not natural kernel reap failure',
              'whole_descendant_settlement': 'unproven', 'production_startup_and_Cargo': 'not established by these controls'}
    e.save(root/'summary.json', report)
    print(json.dumps(report))

if __name__ == '__main__': run(Path(sys.argv[1]))
