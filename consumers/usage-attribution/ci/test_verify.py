#!/usr/bin/env python3
"""Synthetic validation controls, not Rust or Core execution."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import os
import shutil
import tempfile
from unittest.mock import patch
import unittest
spec = importlib.util.spec_from_file_location('verify', Path(__file__).with_name('verify.py'))
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


class Controls(unittest.TestCase):
    def log(self): return 'test one ... ok\ntest two ... ok\ntest result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s\n'
    def reject(self, text):
        with self.assertRaises(ValueError): v.tests(text, ['one', 'two'])
    def test_exact_names(self): self.assertEqual(v.tests(self.log(), ['one', 'two'])['count'], 2)
    def test_missing_name(self): self.reject(self.log().replace('test one ... ok\n', ''))
    def test_duplicate_name(self): self.reject(self.log()+'test one ... ok\n')
    def test_wrong_name(self): self.reject(self.log().replace('test one ', 'test three '))
    def test_wrong_count(self): self.reject(self.log().replace('2 passed', '3 passed'))
    def test_ignored(self): self.reject(self.log().replace('0 ignored', '1 ignored'))
    def test_filtered(self): self.reject(self.log().replace('0 filtered', '1 filtered'))
    def test_failed(self): self.reject(self.log().replace('test one ... ok', 'test one ... FAILED'))
    def test_missing_summary(self): self.reject(self.log().split('test result:')[0])
    def test_duplicate_summary(self): self.reject(self.log()+self.log().splitlines()[-1]+'\n')
    def test_bool_not_int(self): self.assertFalse(v.exact({'n': True}, {'n': 1}))
    def test_float_not_int(self): self.assertFalse(v.exact({'n': 1.0}, {'n': 1}))
    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError): json.loads('{"a":1,"a":2}', object_pairs_hook=v.pairs)
    def test_expected_fixture(self):
        data=v.load(Path(__file__).parents[1]/'fixtures/expected-report.json'); v.fixture(data, data)
    def test_forged_equality_arithmetic(self):
        data=v.load(Path(__file__).parents[1]/'fixtures/expected-report.json'); data['report']['totals']['known_total_tokens']=999
        with self.assertRaises(ValueError): v.fixture(data, copy.deepcopy(data))
    def test_forged_numeric_type(self):
        data=v.load(Path(__file__).parents[1]/'fixtures/expected-report.json'); changed=copy.deepcopy(data); changed['report']['source_revision']=41.0
        with self.assertRaises(ValueError): v.fixture(changed, data)


class Bundle(unittest.TestCase):
    """Entire synthetic bundle; no child process or Rust execution."""
    def save(self, path, data): path.write_text(json.dumps(data)+'\n')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.workspace=self.root/'consumers/usage-attribution'
        shutil.copytree(Path(__file__).parents[1],self.workspace)
        workflow=self.root/'.github/workflows/check-usage-attribution.yml';workflow.parent.mkdir(parents=True)
        workflow.write_bytes((Path(__file__).parents[3]/'.github/workflows/check-usage-attribution.yml').read_bytes())
        self.artifacts=self.root/'artifacts';self.artifacts.mkdir()
        env=patch.dict(os.environ,{'CARGO_TARGET_DIR':str(self.root/'target')});env.start();self.addCleanup(env.stop)
        binary=v.c.binary_path();binary.parent.mkdir(parents=True);binary.write_bytes(b'synthetic-not-executed-binary')
        self.save(self.artifacts/'binary.json',v.c.binary_identity());self.save(self.artifacts/'binary-after.json',v.c.binary_identity())
        identity=v.c.source_identity(self.workspace)
        self.save(self.artifacts/'source-before.json',identity);self.save(self.artifacts/'source-after.json',identity)
        self.save(self.artifacts/'commands.json',[{'label':label,'argv':argv,'returncode':2 if label=='invalid' else 0} for label,argv in v.c.plan(self.workspace)])
        names=v.load(self.workspace/'expected-tests.json')['test_names']
        for target,subset in [('projection',names[:31]),('stdio',names[31:])]:
            (self.artifacts/(target+'.stdout')).write_text(''.join('test '+n+' ... ok\n' for n in subset)+f'test result: ok. {len(subset)} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.1s\n')
        for label,file in [('envelope-controls','test_envelope.py'),('validator-controls','test_verify.py')]:
            names=v.python_names(self.workspace/'ci'/file)
            (self.artifacts/(label+'.stderr')).write_text(''.join(f'{name} (__main__.{cls}.{name}) ... ok\n' for name,cls in names)+f'\nRan {len(names)} tests in 0.001s\n\nOK\n')
        (self.artifacts/'fixture.stdout').write_bytes((self.workspace/'fixtures/expected-report.json').read_bytes())
        (self.artifacts/'fixture.stderr').write_bytes(b'')
        (self.artifacts/'null.stdout').write_bytes(b'{"availability":"unavailable","schema_version":1,"reason":"snapshot_not_available"}\n')
        (self.artifacts/'null.stderr').write_bytes(b'')
        (self.artifacts/'invalid.stdout').write_bytes(b'')
        (self.artifacts/'invalid.stderr').write_bytes(b'invalid usage snapshot payload\n')
        cases=['success','nonzero','timeout','output_cap','inherited_pipe','injected_wait_failure']
        live=self.artifacts/'live';live.mkdir();self.save(live/'summary.json',{'status':'passed','count':6,'cases':cases})
        for case in cases:
            leaf=live/case;leaf.mkdir()
            out=b'fixture-ok\n' if case=='success' else b'x'*4096 if case=='output_cap' else b''
            err=b'fixture-nonzero\n' if case=='nonzero' else b''
            (leaf/'stdout.bin').write_bytes(out);(leaf/'stderr.bin').write_bytes(err)
            cleanup=None if case in ('success','nonzero') else {'all_descendant_termination':'unproven','signals':[{'signal':s,'result':'sent'} for s in ('SIGTERM','SIGKILL')],'direct_child':'unproven' if case=='injected_wait_failure' else 'reaped'}
            if case=='injected_wait_failure':cleanup['wait_error']='TimeoutExpired'
            receipt={'case':case,'reason':{'success':None,'nonzero':'failed_command','output_cap':'stopped_pipe_limit'}.get(case,'stopped_deadline'),
                     'status':'passed' if case=='success' else 'failed','sample_count':2,'minimum_observed_free_bytes':8*1024**3,'elapsed_seconds':0.5,
                     'fixture_identity':{'pid':123,'pgid':123,'ready':True},'all_descendant_termination':'unproven','drain_errors':[],
                     'captured_bytes':{'stdout':len(out),'stderr':len(err)},'returncode':{'success':0,'nonzero':23,'inherited_pipe':0,'injected_wait_failure':None}.get(case,-15),
                     'cleanup':cleanup,'truncated_pipes':['stdout'] if case=='output_cap' else []}
            if case=='injected_wait_failure':receipt['injected_wait_reconciled']=True
            self.save(leaf/'result.json',receipt)
    def reject(self):
        with self.assertRaises((ValueError,KeyError,FileNotFoundError)):v.verify(self.workspace,self.artifacts)
    def mutate(self,name,edit):
        p=self.artifacts/name;data=v.load(p);edit(data);self.save(p,data)
    def test_full_positive(self):self.assertEqual(v.verify(self.workspace,self.artifacts)['named_rust_total'],37)
    def test_full_partial_equal_source_maps(self):
        for name in ('source-before.json','source-after.json'):self.mutate(name,lambda d:d.pop('src/lib.rs'))
        self.reject()
    def test_full_changed_source_bytes(self):
        (self.workspace/'src/lib.rs').write_text('changed');self.reject()
    def test_full_wrong_argv(self):self.mutate('commands.json',lambda d:d[7]['argv'].append('--unlocked'));self.reject()
    def test_full_wrong_exit_type(self):self.mutate('commands.json',lambda d:d[0].update(returncode=False));self.reject()
    def test_full_forged_binary_hash(self):
        for name in ('binary.json','binary-after.json'):self.mutate(name,lambda d:d.update(sha256='a'*64))
        self.reject()
    def test_full_post_binary_change(self):v.c.binary_path().write_bytes(b'changed');self.reject()
    def test_full_missing_helper(self):
        p=self.artifacts/'envelope-controls.stderr';p.write_text('\n'.join(p.read_text().splitlines()[1:]));self.reject()
    def test_full_helper_skip(self):
        p=self.artifacts/'validator-controls.stderr';p.write_text(p.read_text().replace('... ok','... skipped',1));self.reject()
    def test_full_extra_skipped_helper(self):
        p=self.artifacts/'validator-controls.stderr';p.write_text(p.read_text().replace('\nOK\n',"\ntest_extra (__main__.Controls.test_extra) ... skipped 'injected'\nOK\n"));self.reject()
    def test_full_extra_expected_failure_helper(self):
        p=self.artifacts/'validator-controls.stderr';p.write_text(p.read_text().replace('\nOK\n','\ntest_extra (__main__.Controls.test_extra) ... expected failure\nOK\n'));self.reject()
    def test_full_missing_live_receipt(self):(self.artifacts/'live/timeout/result.json').unlink();self.reject()
    def test_full_wrong_live_reason(self):self.mutate('live/timeout/result.json',lambda d:d.update(reason=None));self.reject()
    def test_full_injected_wait_not_reconciled(self):self.mutate('live/injected_wait_failure/result.json',lambda d:d.update(injected_wait_reconciled=False));self.reject()
    def test_full_wrong_capture_size(self):self.mutate('live/output_cap/result.json',lambda d:d['captured_bytes'].update(stdout=4095));self.reject()
    def test_full_reap_not_proven(self):self.mutate('live/timeout/result.json',lambda d:d['cleanup'].update(direct_child='unproven'));self.reject()
    def test_full_fixture_integer_is_float(self):self.mutate('fixture.stdout',lambda d:d['report'].update(source_revision=41.0));self.reject()
    def test_full_partial_refusal_output(self):(self.artifacts/'invalid.stdout').write_bytes(b'partial');self.reject()

if __name__ == '__main__': unittest.main(verbosity=2)
