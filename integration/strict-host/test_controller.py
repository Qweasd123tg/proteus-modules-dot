#!/usr/bin/env python3
"""Five authored controller controls; not Core/module/runtime evidence."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest

if len(sys.argv)>1 and sys.argv[1]=='--child':
    mode=sys.argv[2]
    if mode in ('detached','orphan'):
        pid=os.fork()
        if pid==0:
            os.setsid()
            print('owned detached child',flush=True)
            time.sleep(30)
            os._exit(0)
        if mode=='orphan': os._exit(0)
    if mode in ('timeout','detached'): time.sleep(30)
    if mode=='nonzero': sys.exit(7)
    print('authored control',flush=True)
    sys.exit(0)

OUT=Path(sys.argv.pop(1)).resolve()
OUT.mkdir(parents=False,exist_ok=False)
spec=importlib.util.spec_from_file_location('owned_host_controller',Path(__file__).with_name('run_host.py'))
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.subreaper()

class Controls(unittest.TestCase):
    def run_case(self,mode,timeout=2):
        directory=OUT/mode;directory.mkdir()
        result=runner.capture([sys.executable,'-B','-I',str(Path(__file__).resolve()),'--child',mode],directory,{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},directory/'stdout',directory/'stderr',timeout)
        (directory/'result.json').write_text(json.dumps(result,indent=2))
        self.assertIsNone(result['cleanup_error'])
        self.assertIsNone(result['capture_error'])
        self.assertFalse(result['disk_guard_stopped'])
        self.assertEqual(result['remaining_owned_children'],[])
        self.assertLess(result['wall_seconds'],timeout+6)
        return result
    def test_normal(self):
        r=self.run_case('normal');self.assertEqual(r['returncode'],0);self.assertFalse(r['timed_out'])
    def test_nonzero(self):
        r=self.run_case('nonzero');self.assertEqual(r['returncode'],7);self.assertFalse(r['timed_out'])
    def test_timeout(self):
        r=self.run_case('timeout',0.15);self.assertTrue(r['timed_out']);self.assertNotEqual(r['returncode'],0)
    def test_detached_process_group(self):
        r=self.run_case('detached',0.2);self.assertTrue(r['timed_out']);self.assertGreaterEqual(len(r['owned_processes']),2)
        self.assertGreaterEqual(len({p['pgid'] for p in r['owned_processes']}),2)
    def test_orphan_adoption(self):
        r=self.run_case('orphan');self.assertEqual(r['returncode'],0);self.assertFalse(r['timed_out'])
        self.assertGreaterEqual(len(r['owned_processes']),2)
        self.assertTrue(r['adopted_descendants'])
        self.assertTrue(all(p['pid']!=r['root_pid'] for p in r['adopted_descendants']))
        self.assertTrue(any(p['pid']!=r['root_pid'] and p.get('pgid')==p['pid'] for p in r['owned_processes']))

if __name__=='__main__':unittest.main()
