#!/usr/bin/env python3
"""Pure synthetic prerequisite-gate controls; no child or Rust execution."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('gate',Path(__file__).with_name('verify_ci.py'))
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.log=self.root/'log'
        self.expected={'fixture':['first','second'],'mock':['test_first','test_second']}

    def rust(self):
        self.log.write_text('running 2 tests\ntest first ... ok\ntest second ... ok\ntest result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s\n')
        g.tests('fixture',self.log,self.expected)

    def python(self):
        self.log.write_text('test_first (__main__.Controls.test_first) ... ok\ntest_second (__main__.Controls.test_second) ... ok\nRan 2 tests in 0.001s\n\nOK\n')
        g.tests('mock',self.log,self.expected)

    def test_rust_exact_valid(self): self.rust()
    def test_python_exact_valid(self): self.python()
    def test_rust_wrong_name_rejected(self):
        self.rust();self.log.write_text(self.log.read_text().replace('test second','test surprise'))
        with self.assertRaisesRegex(ValueError,'test-name'):g.tests('fixture',self.log,self.expected)
    def test_rust_duplicate_rejected(self):
        self.rust();self.log.write_text(self.log.read_text().replace('test second','test first'))
        with self.assertRaisesRegex(ValueError,'test-name'):g.tests('fixture',self.log,self.expected)
    def test_rust_ignored_rejected(self):
        self.rust();self.log.write_text(self.log.read_text().replace('0 ignored','1 ignored'))
        with self.assertRaisesRegex(ValueError,'count/status'):g.tests('fixture',self.log,self.expected)
    def test_rust_duplicate_summary_rejected(self):
        self.rust();self.log.write_text(self.log.read_text()+self.log.read_text().splitlines()[-1]+'\n')
        with self.assertRaisesRegex(ValueError,'count/status'):g.tests('fixture',self.log,self.expected)
    def test_rust_extra_ignored_row_rejected(self):
        self.rust();self.log.write_text(self.log.read_text()+'test surprise ... ignored\n')
        with self.assertRaisesRegex(ValueError,'non-ok Rust'):g.tests('fixture',self.log,self.expected)
    def test_rust_extra_failed_row_rejected(self):
        self.rust();self.log.write_text(self.log.read_text()+'test surprise ... FAILED\n')
        with self.assertRaisesRegex(ValueError,'non-ok Rust'):g.tests('fixture',self.log,self.expected)
    def test_python_missing_rejected(self):
        self.python();self.log.write_text(self.log.read_text().replace('test_second (__main__.Controls.test_second) ... ok\n',''))
        with self.assertRaisesRegex(ValueError,'test-name'):g.tests('mock',self.log,self.expected)
    def test_python_skip_rejected(self):
        self.python();self.log.write_text(self.log.read_text().replace('OK','OK (skipped=1)'))
        with self.assertRaisesRegex(ValueError,'finish OK'):g.tests('mock',self.log,self.expected)
    def test_python_resource_warning_rejected(self):
        self.python();self.log.write_text('ResourceWarning: subprocess still running\n'+self.log.read_text())
        with self.assertRaisesRegex(ValueError,'warning/failure'):g.tests('mock',self.log,self.expected)
    def test_python_duplicate_summary_rejected(self):
        self.python();self.log.write_text('Ran 2 tests in 0.001s\n'+self.log.read_text())
        with self.assertRaisesRegex(ValueError,'count mismatch'):g.tests('mock',self.log,self.expected)
    def test_python_extra_non_ok_row_rejected(self):
        self.python();self.log.write_text('test_surprise (__main__.Controls.test_surprise) ... expected failure\n'+self.log.read_text())
        with self.assertRaisesRegex(ValueError,'non-ok Python'):g.tests('mock',self.log,self.expected)
    def test_source_changed_rejected(self):
        ci=self.root/'ci/strict-fullturn';ci.mkdir(parents=True)
        f=self.root/'fixture';f.write_text('original')
        (ci/'PUBLICATION.json').write_text(json.dumps({'payload_sha256':{'fixture':g.sha(f)}}))
        g.sources(self.root,self.root/'before');f.write_text('changed')
        with self.assertRaisesRegex(ValueError,'source mismatch'):g.sources(self.root,self.root/'after')
    def test_graph_other_sdk_rejected(self):
        official=self.root/'official';official.mkdir();(official/'Cargo.lock').write_text('authored')
        for name in ('host','fixture','strict','official'):
            pin=g.SDK if name=='official' else g.CORE
            (self.root/('metadata-'+name+'.json')).write_text(json.dumps({'packages':[{'source':'git+https://github.com/Proteus-harness/Proteus-core?rev='+pin+'#'+pin}]}))
        with patch.object(g,'LOCK',g.sha(official/'Cargo.lock')):
            g.graphs(self.root,official)
            f=self.root/'metadata-official.json';f.write_text(f.read_text().replace(g.SDK,g.CORE))
            with self.assertRaisesRegex(ValueError,'mixed Core graph'):g.graphs(self.root,official)

    def live(self):
        live=self.root/'live';live.mkdir()
        for name in ('normal','nonzero','timeout','detached','orphan'):
            d=live/name;d.mkdir()
            for stream in ('stdout','stderr'):(d/stream).write_text('authored synthetic '+name)
            r={'timed_out':name in ('timeout','detached'),'returncode':7 if name=='nonzero' else -15 if name in ('timeout','detached') else 0,
               'cleanup_error':None,'capture_error':None,'inspection_errors':[],'remaining_owned_children':[],
               'direct_child_cleanup_fallback':False,'disk_guard_stopped':False,
               'owned_processes':[{'pid':100,'pgid':100},{'pid':101,'pgid':101}],
               'adopted_descendants':[{'pid':101,'start_time':1}],
               'stdout_sha256':g.sha(d/'stdout'),'stderr_sha256':g.sha(d/'stderr')}
            (d/'result.json').write_text(json.dumps(r))
        g.live(live)
        return live

    def corrupt_live(self,key,value,diagnostic):
        live=self.live();f=live/'orphan/result.json';r=json.loads(f.read_text());r[key]=value;f.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,diagnostic):g.live(live)
    def test_live_synthetic_valid(self):self.live()
    def test_live_cleanup_error_rejected(self):self.corrupt_live('cleanup_error','unknown','cleanup/capture')
    def test_live_remaining_child_rejected(self):self.corrupt_live('remaining_owned_children',[101],'cleanup unknown')
    def test_live_missing_adoption_rejected(self):self.corrupt_live('adopted_descendants',[],'adoption')
    def test_live_output_digest_rejected(self):self.corrupt_live('stdout_sha256','0'*64,'identity mismatch')


if __name__=='__main__':unittest.main()
