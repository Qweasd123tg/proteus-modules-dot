#!/usr/bin/env python3
"""Pure filesystem/mocked process controls: no Cargo, child, or signal is run."""
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("envelope", Path(__file__).with_name("envelope.py"))
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class Files(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / '.hidden|owned').write_bytes(b'authored')

    def test_valid_hidden_vertical_bar_snapshot(self):
        result = e.snapshot(self.source, self.root / 'copy')
        self.assertEqual(result['.hidden|owned']['bytes'], 8)
        with tarfile.open(self.root/'copy') as archive:
            self.assertEqual(archive.getnames(), ['.hidden|owned'])
            self.assertEqual(archive.extractfile('.hidden|owned').read(), b'authored')

    def test_file_cap_from_valid_baseline(self):
        e.inventory(self.source)
        with patch.object(e, 'MAX_FILE', 7):
            with self.assertRaisesRegex(ValueError, 'artifact file exceeds limit'):
                e.inventory(self.source)

    def test_aggregate_cap_from_valid_baseline(self):
        e.inventory(self.source)
        with patch.object(e, 'MAX_ARTIFACTS', 7):
            with self.assertRaisesRegex(ValueError, 'artifact aggregate exceeds limit'):
                e.inventory(self.source)

    def test_count_cap_from_valid_baseline(self):
        e.inventory(self.source)
        with patch.object(e, 'MAX_ENTRIES', 0):
            with self.assertRaisesRegex(ValueError, 'artifact entry count exceeds limit'):
                e.inventory(self.source)

    def test_path_cap_from_valid_baseline(self):
        e.inventory(self.source)
        with patch.object(e, 'MAX_PATH_BYTES', 2):
            with self.assertRaisesRegex(ValueError, 'artifact relative path exceeds limit'):
                e.inventory(self.source)

    def test_depth_cap(self):
        (self.source/'child').mkdir()
        e.inventory(self.source)
        with patch.object(e, 'MAX_DEPTH', 0):
            with self.assertRaisesRegex(ValueError, 'artifact depth exceeds limit'):
                e.inventory(self.source)

    def test_symlink_rejected(self):
        e.inventory(self.source)
        (self.source/'link').symlink_to(self.source/'.hidden|owned')
        with self.assertRaisesRegex(ValueError, 'artifact contains nonregular'):
            e.inventory(self.source)

    def test_root_symlink_rejected(self):
        alias = self.root/'alias'; alias.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'artifact root must be a real directory'):
            e.inventory(alias)

    def test_bounded_read_exact_and_plus_one(self):
        self.assertEqual(e.bounded_read(self.source/'.hidden|owned', 8), b'authored')
        with self.assertRaisesRegex(ValueError, 'input is not a bounded regular file'):
            e.bounded_read(self.source/'.hidden|owned', 7)

    def test_snapshot_metadata_race(self):
        real = e.inventory(self.source)
        with patch.object(e, 'inventory', side_effect=[real, {}]):
            with self.assertRaisesRegex(ValueError, 'artifact metadata changed'):
                e.snapshot(self.source, self.root/'copy')

    def test_snapshot_size_race(self):
        e.inventory(self.source)
        with patch.object(e, 'bounded_read', return_value=b'changed size'):
            with self.assertRaisesRegex(ValueError, 'artifact changed during snapshot'):
                e.snapshot(self.source, self.root/'copy')

    def test_low_disk_never_spawns(self):
        with patch.object(e.shutil, 'disk_usage', return_value=SimpleNamespace(free=e.INITIAL_FREE-1)), patch.object(e.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'below 8 GiB'):
                e.execute('cas-lock-resolution', self.root, self.root/'output', self.root/'future', [], ['authored-mock'])
            spawn.assert_not_called()
            self.assertFalse((self.root/'output').exists())

    def test_old_output_never_spawns(self):
        with patch.object(e.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'must both be fresh'):
                e.execute('cas-lock-resolution', self.root, self.source, self.root/'future', [], ['authored-mock'])
            spawn.assert_not_called()

    def test_nested_output_never_spawns(self):
        with patch.object(e.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'must be disjoint'):
                e.execute('cas-lock-resolution', self.root, self.root/'future', self.root/'future/child', [], ['authored-mock'])
            spawn.assert_not_called()

    def test_input_count_bounded(self):
        with self.assertRaisesRegex(ValueError, 'too many explicit'):
            e.input_hashes([self.source/'.hidden|owned']*(e.MAX_INPUTS+1))

    def test_spawn_error_has_receipt(self):
        with patch.object(e.shutil, 'disk_usage', return_value=SimpleNamespace(free=e.INITIAL_FREE)), patch.object(e.subprocess, 'Popen', side_effect=OSError('authored')):
            result = e.execute('cas-lock-resolution', self.root, self.root/'out', self.root/'future', [], ['authored-mock'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['reason'], 'OSError')
        self.assertTrue((self.root/'out/result.json').is_file())

    def test_success_has_fresh_marker_and_bounded_archive(self):
        def supervised(process, artifact_root, output, timeout):
            artifact_root.mkdir(); (artifact_root/'status.txt').write_text('passed\n')
            return {'status': 'passed', 'returncode': 0, 'all_descendant_termination': 'unproven'}
        with patch.object(e.shutil, 'disk_usage', return_value=SimpleNamespace(free=e.INITIAL_FREE)), patch.object(e.subprocess, 'Popen', return_value=Mock()), patch.object(e, 'supervise', side_effect=supervised):
            result=e.execute('cas-lock-resolution',self.root,self.root/'out',self.root/'child',[],['authored-mock'])
        import json
        marker=json.loads((self.root/'out/invocation.json').read_text())
        self.assertEqual(marker['invocation_id'],result['invocation_id'])
        self.assertEqual(result['status'],'passed')
        self.assertEqual(set(result['snapshot_files']),{'status.txt'})
        with tarfile.open(self.root/'out/artifacts.tar') as archive:
            self.assertEqual(archive.extractfile('status.txt').read(),b'passed\n')

    def test_changed_input_keeps_command_success_separate(self):
        def supervised(process, artifact_root, output, timeout):
            artifact_root.mkdir(); (artifact_root/'status.txt').write_text('passed\n')
            return {'status':'passed','returncode':0}
        with patch.object(e.shutil,'disk_usage',return_value=SimpleNamespace(free=e.INITIAL_FREE)), patch.object(e.subprocess,'Popen',return_value=Mock()), patch.object(e,'supervise',side_effect=supervised), patch.object(e,'input_hashes',side_effect=[{'a':'old'},{'a':'new'}]):
            result=e.execute('cas-lock-resolution',self.root,self.root/'out',self.root/'child',[],['authored-mock'])
        self.assertEqual(result['status'],'failed');self.assertEqual(result['source_error'],'controller_inputs_changed');self.assertEqual(result['returncode'],0)

    def test_partial_archive_enumerates_retained_only(self):
        (self.source/'second').write_bytes(b'other')
        manifest={};original=e.bounded_read
        def read(path, limit):
            if path.name=='second': raise ValueError('authored snapshot failure')
            return original(path,limit)
        with patch.object(e,'bounded_read',side_effect=read):
            with self.assertRaisesRegex(ValueError,'authored snapshot failure'):
                e.snapshot(self.source,self.root/'copy',manifest)
        self.assertEqual(set(manifest),{'.hidden|owned'})
        with tarfile.open(self.root/'copy') as archive:
            self.assertEqual(archive.getnames(),['.hidden|owned'])

    def test_snapshot_low_headroom_is_failed_not_success(self):
        with patch.object(e.shutil,'disk_usage',side_effect=[SimpleNamespace(free=e.INITIAL_FREE),SimpleNamespace(free=e.STOP_FREE-1)]),patch.object(e.subprocess,'Popen',return_value=Mock()),patch.object(e,'supervise',return_value={'status':'passed','returncode':0}):
            result=e.execute('cas-lock-resolution',self.root,self.root/'out',self.root/'child',[],['authored-mock'])
        self.assertEqual(result['status'],'failed');self.assertEqual(result['snapshot_status'],'failed_or_partial')
        self.assertIn('insufficient snapshot headroom',result['snapshot_error'])

    def test_different_filesystem_refused_before_spawn(self):
        with patch.object(e,'device',side_effect=[1,2,1]),patch.object(e.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'must share the monitored filesystem'):
                e.execute('cas-lock-resolution',self.root,self.root/'out',self.root/'child',[],['authored-mock'])
            spawn.assert_not_called()

    def test_primary_deadline_survives_source_mismatch(self):
        def supervised(process, artifact_root, output, timeout):
            artifact_root.mkdir()
            return {'status':'failed','reason':'stopped_deadline','returncode':-9}
        with patch.object(e.shutil,'disk_usage',return_value=SimpleNamespace(free=e.INITIAL_FREE)),patch.object(e.subprocess,'Popen',return_value=Mock()),patch.object(e,'supervise',side_effect=supervised),patch.object(e,'input_hashes',side_effect=[{'a':'old'},{'a':'new'}]):
            result=e.execute('cas-lock-resolution',self.root,self.root/'out',self.root/'child',[],['authored-mock'])
        self.assertEqual(result['reason'],'stopped_deadline');self.assertEqual(result['source_error'],'controller_inputs_changed')

    def test_final_receipt_failure_gets_explicit_partial_fallback(self):
        original=e.save
        def save(path,value):
            if path.name=='result.json': raise OSError('authored write failure')
            original(path,value)
        with patch.object(e.shutil,'disk_usage',return_value=SimpleNamespace(free=e.INITIAL_FREE)),patch.object(e.subprocess,'Popen',side_effect=OSError('authored spawn failure')),patch.object(e,'save',side_effect=save):
            result=e.execute('cas-lock-resolution',self.root,self.root/'out',self.root/'child',[],['authored-mock'])
        self.assertEqual(result['status'],'failed');self.assertEqual(result['receipt_error'],'OSError')
        self.assertTrue((self.root/'out/incomplete-result.json').exists())


class Cleanup(unittest.TestCase):
    def test_term_kill_before_any_reap(self):
        p=Mock(pid=812, returncode=None); order=[]
        def send(pid, sig):
            self.assertEqual(pid, 812); p.wait.assert_not_called(); p.poll.assert_not_called(); order.append(sig.name)
        def wait(timeout):
            self.assertEqual(timeout, 5); order.append('reap'); p.returncode=-9
        p.wait.side_effect=wait
        with patch.object(e.os, 'killpg', side_effect=send), patch.object(e.time, 'sleep') as sleep:
            result=e.stop(p)
        self.assertEqual(order,['SIGTERM','SIGKILL','reap'])
        sleep.assert_called_once_with(0.25)
        self.assertEqual(result['all_descendant_termination'],'unproven')

    def test_reaped_group_not_signaled(self):
        p=Mock(returncode=0)
        with patch.object(e.os,'killpg') as kill:
            result=e.stop(p)
        kill.assert_not_called(); p.wait.assert_not_called()
        self.assertIn('numeric group not signaled',result['direct_child'])

    def test_signal_denial_still_attempts_reap(self):
        p=Mock(pid=812, returncode=None)
        with patch.object(e.os,'killpg',side_effect=PermissionError), patch.object(e.time,'sleep'):
            result=e.stop(p)
        self.assertEqual([x['result'] for x in result['signals']],['signal_error']*2)
        p.wait.assert_called_once_with(timeout=5)

    def test_wait_timeout_does_not_claim_settlement(self):
        p=Mock(pid=812, returncode=None); p.wait.side_effect=subprocess.TimeoutExpired('mock',5)
        with patch.object(e.os,'killpg'), patch.object(e.time,'sleep'):
            result=e.stop(p)
        self.assertEqual(result['direct_child'],'unproven')


class Capture(unittest.TestCase):
    def call(self, scenario):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); p=Mock(pid=812,returncode=None)
            p.stdout=Mock();p.stderr=Mock()
            selector=Mock(); selector.get_map.return_value={'open': True}
            free=e.STOP_FREE+1; times=iter([0,1,2,3,4,5,6,7])
            data=b'owned'
            if scenario=='deadline': times=iter([0,9,10])
            if scenario=='disk': free=e.STOP_FREE-1
            if scenario=='success':
                selector.get_map.return_value={}; p.poll.return_value=0;p.returncode=0
            if scenario=='nonzero':
                selector.get_map.return_value={}; p.poll.return_value=7;p.returncode=7
            if scenario=='pipe':
                selector.select.return_value=[(SimpleNamespace(fileobj=p.stdout,data='stdout'),1)];data=b'x'*17
            def scan(_):
                if scenario=='artifact': raise ValueError('artifact aggregate exceeds limit')
                return {}
            with patch.object(e.selectors,'DefaultSelector',return_value=selector),patch.object(e.os,'set_blocking'),patch.object(e.os,'read',return_value=data),patch.object(e.os,'killpg'),patch.object(e.time,'sleep'),patch.object(e.time,'monotonic',side_effect=lambda:next(times)),patch.object(e.shutil,'disk_usage',return_value=SimpleNamespace(free=free)),patch.object(e,'inventory',side_effect=scan),patch.object(e,'MAX_PIPE',16):
                result=e.supervise(p,root/'artifacts',root,5)
            return result

    def test_deadline(self): self.assertEqual(self.call('deadline')['reason'],'stopped_deadline')
    def test_disk(self): self.assertEqual(self.call('disk')['reason'],'stopped_disk_guard')
    def test_pipe(self):
        r=self.call('pipe');self.assertEqual(r['reason'],'stopped_pipe_limit');self.assertEqual(r['captured_bytes']['stdout'],16)
    def test_artifact(self): self.assertEqual(self.call('artifact')['reason'],'artifact aggregate exceeds limit')
    def test_success_is_not_tree_settlement(self):
        r=self.call('success');self.assertEqual(r['status'],'passed');self.assertEqual(r['all_descendant_termination'],'unproven')
    def test_nonzero(self): self.assertEqual(self.call('nonzero')['reason'],'failed_command')

    def test_unconfirmed_nonblocking_setup_never_reads_pipe(self):
        with tempfile.TemporaryDirectory() as root:
            p=Mock(pid=812,returncode=None)
            with patch.object(e.os,'set_blocking',side_effect=OSError('authored unavailable')),patch.object(e.os,'read') as read,patch.object(e.os,'killpg'),patch.object(e.time,'sleep'):
                result=e.supervise(p,Path(root)/'child',Path(root),5)
            read.assert_not_called();p.wait.assert_called_once_with(timeout=5)
            self.assertEqual(result['status'],'failed');self.assertEqual(result['reason'],'OSError')

    def test_initial_monitor_error_closes_selector_and_attempts_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            p=Mock(pid=812,returncode=None);selector=Mock()
            with patch.object(e.selectors,'DefaultSelector',return_value=selector),patch.object(e.shutil,'disk_usage',side_effect=OSError('authored stat error')),patch.object(e.os,'read') as read,patch.object(e.os,'killpg'),patch.object(e.time,'sleep'):
                result=e.supervise(p,Path(root)/'child',Path(root),5)
            selector.close.assert_called_once();read.assert_not_called();p.wait.assert_called_once_with(timeout=5)
            self.assertEqual(result['reason'],'OSError')


if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    raise SystemExit(0 if r.wasSuccessful() and r.testsRun==35 and not r.skipped else 1)
