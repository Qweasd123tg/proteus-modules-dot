#!/usr/bin/env python3
"""Pure mocks of controller failures; no child, pidfd or signal is created."""
import importlib.util
import itertools
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

OUT=Path(sys.argv.pop(1)).resolve();OUT.mkdir(parents=False,exist_ok=False)
spec=importlib.util.spec_from_file_location('host_controller_mock_target',Path(__file__).with_name('run_host.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class Controls(unittest.TestCase):
    def setUp(self):
        self.space=mock.patch.object(r.shutil,'disk_usage',return_value=type('Disk',(),{'free':4*1024**3})())
        self.space.start();self.addCleanup(self.space.stop)
    def test_disk_guard_refuses_before_spawn(self):
        directory=OUT/'disk';directory.mkdir()
        with mock.patch.object(r.shutil,'disk_usage',return_value=type('Disk',(),{'free':r.STOP_FREE-1})()),mock.patch.object(r,'identities',return_value=set()),mock.patch.object(r.subprocess,'Popen') as spawn:
            result=r.capture(['not-executed'],directory,{},directory/'stdout',directory/'stderr',.1)
        spawn.assert_not_called();self.assertTrue(result['disk_guard_stopped'])
        self.assertIn('disk reserve guard before spawn',result['capture_error'])
        (directory/'result.json').write_text(json.dumps(result,indent=2))
    def test_missing_child_lists_fails_before_pidfd(self):
        with mock.patch.object(r.Path,'glob',return_value=[]),mock.patch.object(r.os,'pidfd_open') as opened:
            with self.assertRaisesRegex(RuntimeError,'children lists unavailable'):r.subreaper()
            opened.assert_not_called()
    def test_missing_task_directory_with_live_identity_is_unknown(self):
        with mock.patch.object(r.Path,'iterdir',side_effect=FileNotFoundError()),mock.patch.object(r,'identity',return_value={'pid':12345}):
            with self.assertRaisesRegex(RuntimeError,'task directory unavailable'):r.identities(12345)
    def test_direct_child_cleanup_if_pidfd_open_fails(self):
        directory=OUT/'pidfd';directory.mkdir()
        class Process:
            pid=12345
            returncode=None
            def poll(self):return self.returncode
            def wait(self,timeout):return self.returncode
            def send_signal(self,sig):self.returncode=-int(sig)
        process=Process()
        me={'pid':os.getpid(),'start_time':1,'ppid':0,'pgid':1,'state':'R'}
        with mock.patch.object(r,'identities',return_value=set()),mock.patch.object(r.subprocess,'Popen',return_value=process),mock.patch.object(r.os,'pidfd_open',side_effect=OSError('authored fd exhaustion')),mock.patch.object(r,'identity',return_value=me),mock.patch.object(r.time,'sleep'),mock.patch.object(r.time,'monotonic',side_effect=itertools.count()):
            result=r.capture(['not-executed'],directory,{},directory/'stdout',directory/'stderr',.1)
        self.assertIn('authored fd exhaustion',result['capture_error'])
        self.assertTrue(result['direct_child_cleanup_fallback'])
        self.assertLess(result['returncode'],0)
        (directory/'result.json').write_text(json.dumps(result,indent=2))
    def test_root_fd_retained_if_identity_read_fails(self):
        own=r.Owned()
        with mock.patch.object(r.os,'pidfd_open',return_value=77),mock.patch.object(r,'identity',side_effect=PermissionError('authored read denied')):
            with self.assertRaises(PermissionError):own.register_root(12345)
        self.assertEqual(own.handles,{(12345,None):77})
        with mock.patch.object(r.signal,'pidfd_send_signal') as send:
            self.assertEqual(own.terminate(r.signal.SIGTERM),[])
            send.assert_called_once_with(77,r.signal.SIGTERM,None,0)
    def test_reused_parent_is_not_traversed(self):
        me=os.getpid();child=987654
        child_reads=iter((1,1,2))
        def identity(pid):
            return {'pid':pid,'start_time':1 if pid==me else next(child_reads),'ppid':0 if pid==me else me,'pgid':pid,'state':'S'}
        def children(pid):
            self.assertEqual(pid,me,'replacement parent was traversed')
            return {child}
        own=r.Owned()
        with mock.patch.object(r,'identity',side_effect=identity),mock.patch.object(r,'identities',side_effect=children),mock.patch.object(r.os,'pidfd_open',return_value=77):
            own.discover()
        self.assertEqual(list(own.handles),[(child,1)])
    def test_signal_all_known_fds_despite_one_error(self):
        own=r.Owned();own.handles={(1,1):77,(2,2):88}
        with mock.patch.object(r.signal,'pidfd_send_signal',side_effect=[PermissionError('authored denial'),None]) as send:
            errors=own.terminate(r.signal.SIGTERM)
        self.assertEqual(send.call_count,2);self.assertEqual(errors,['authored denial'])
    def test_spawn_failure_is_recorded(self):
        directory=OUT/'spawn';directory.mkdir()
        with mock.patch.object(r,'identities',return_value=set()),mock.patch.object(r.subprocess,'Popen',side_effect=OSError('authored spawn failure')):
            result=r.capture(['not-executed'],directory,{},directory/'stdout',directory/'stderr',.1)
        self.assertIn('authored spawn failure',result['capture_error'])
        self.assertIsNone(result['returncode'])
        (directory/'result.json').write_text(json.dumps(result,indent=2))
    def test_inspection_failure_keeps_direct_cleanup_and_unknown_receipt(self):
        directory=OUT/'inspection';directory.mkdir()
        class Process:
            pid=12345
            returncode=None
            def poll(self):return self.returncode
            def wait(self,timeout):return self.returncode
        process=Process();signals=[]
        def send(fd,sig,*rest):signals.append((fd,sig));process.returncode=-15
        class Poll:
            def register(self,*args):pass
            def poll(self,*args):return [] if process.returncode is None else [(77,1)]
        with mock.patch.object(r,'identities',return_value=set()),mock.patch.object(r.subprocess,'Popen',return_value=process),mock.patch.object(r.os,'pidfd_open',return_value=77),mock.patch.object(r.os,'close') as close,mock.patch.object(r,'identity',side_effect=PermissionError('authored proc denial')),mock.patch.object(r.signal,'pidfd_send_signal',side_effect=send),mock.patch.object(r.select,'poll',return_value=Poll()),mock.patch.object(r.time,'sleep'),mock.patch.object(r.time,'monotonic',side_effect=itertools.count()):
            result=r.capture(['not-executed'],directory,{},directory/'stdout',directory/'stderr',.1)
        self.assertTrue(signals);self.assertEqual(signals[0][0],77)
        self.assertIn('authored proc denial',result['capture_error'])
        self.assertEqual(result['cleanup_error'],'owned descendant state unknown after inspection error')
        self.assertIsNone(result['remaining_owned_children'])
        close.assert_called_once_with(77)
        (directory/'result.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__':unittest.main()
