#!/usr/bin/env python3
"""Synthetic full-bundle gates and typed example corruption tests; no live process."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('verify_runtime',Path(__file__).with_name('verify_runtime.py'));v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
g=v.g;e=v.example

def example_fixture():
    identity={'schema_version':1,'store_id':'release-proposals','database_instance_id':'1'*32,'workspace_cwd':'/tmp/authored-cas-fixture','database_path':'store/notes.sqlite','policy_sha256':e.digest(e.policy())}
    return e.expected(identity,['nested-'+str(i) for i in range(8)])

class Example(unittest.TestCase):
    def setUp(self):self.report=example_fixture()
    def reject(self):
        with self.assertRaises((ValueError,KeyError)):e.verify(self.report)
    def test_valid_complete_example(self):self.assertTrue(e.verify(self.report)['durable_conflict'])
    def test_wrong_policy(self):self.report['init']['metadata'][e.KEY]['result']['policy_sha256']='f'*64;self.reject()
    def test_boolean_revision(self):self.report['current']['metadata'][e.KEY]['result']['revision']=True;self.reject()
    def test_wrong_conflict(self):self.report['conflict']['metadata'][e.KEY]['result']['outcome']['decision']='applied';self.reject()
    def test_broken_replay(self):self.report['replay']['metadata'][e.KEY]['result']['request']['proposal']['new_text']='modified';self.reject()
    def test_wrong_record_digest(self):self.report['applied']['metadata'][e.KEY]['result']['outcome']['request_sha256']='a'*64;self.reject()
    def test_wrong_observed_path(self):self.report['applied']['metadata'][e.KEY]['result']['observation']['observed_path']='/other/file';self.reject()
    def test_truth_claim(self):self.report['applied']['metadata'][e.KEY]['result']['observation']['semantic_entailment']='verified';self.reject()
    def test_write_authority_claim(self):self.report['applied']['metadata'][e.KEY]['audit']['grants_write_authority']=True;self.reject()
    def test_missing_nested(self):self.report['nested_calls'].pop();self.reject()
    def test_duplicate_call_id(self):self.report['nested_calls'][1]['id']=self.report['nested_calls'][0]['id'];self.reject()
    def test_wrong_reader_args(self):self.report['nested_calls'][1]['args']['path']='elsewhere';self.reject()
    def test_payload_rejection_lost(self):self.report['changed_payload_rejected']['ok']=True;self.reject()
    def test_extra_top_field(self):self.report['extra']=True;self.reject()
    def test_no_core_claim(self):self.report['actual_core']=True;self.reject()

class Bundle(unittest.TestCase):
    def save(self,path,data):path.write_text(json.dumps(data)+'\n')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.w=self.root/'examples/correction-memory';shutil.copytree(Path(__file__).parents[1],self.w)
        spans=self.w.parent/'evidence-spans';spans.mkdir();(spans/'Cargo.toml').write_text('# synthetic dependency payload; never compiled\n')
        workflow=self.root/'.github/workflows/check-correction-memory.yml';workflow.parent.mkdir(parents=True);workflow.write_bytes((Path(__file__).parents[3]/'.github/workflows/check-correction-memory.yml').read_bytes())
        self.a=self.root/'artifacts';self.a.mkdir()
        env=patch.dict(os.environ,{'CARGO_TARGET_DIR':str(self.root/'target')});env.start();self.addCleanup(env.stop)
        for name,path in v.c.binaries().items():path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('not-executed-'+name).encode())
        for name in ('binaries-before.json','binaries-after.json'):self.save(self.a/name,v.c.binary_identity())
        for name in ('source-before.json','source-after.json'):self.save(self.a/name,v.c.source_identity(self.w))
        self.save(self.a/'commands.json',[{'label':label,'argv':argv,'returncode':0} for label,argv in v.c.plan(self.w)])
        expected=g.load(self.w/'ci/expected-tests.json')['targets']
        for target,names in expected.items():
            (self.a/('test-'+target+'.stdout')).write_text(''.join('test '+n+' ... ok\n' for n in names)+f'test result: ok. {len(names)} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s\n')
        for label,file in [('envelope-controls','test_envelope.py'),('validator-controls','test_runtime.py')]:
            names=g.python_names(self.w/'ci'/file);(self.a/(label+'.stderr')).write_text(''.join(f'{name} (__main__.{cls}.{name}) ... ok\n' for name,cls in names)+f'\nRan {len(names)} tests in 0.001s\n\nOK\n')
        cases=['success','nonzero','timeout','output_cap','inherited_pipe','injected_wait_failure'];live=self.a/'live';live.mkdir();self.save(live/'summary.json',{'status':'passed','count':6,'cases':cases})
        for case in cases:
            leaf=live/case;leaf.mkdir();out=b'fixture-ok\n' if case=='success' else b'x'*4096 if case=='output_cap' else b'';err=b'fixture-nonzero\n' if case=='nonzero' else b''
            (leaf/'stdout.bin').write_bytes(out);(leaf/'stderr.bin').write_bytes(err)
            cleanup=None if case in ('success','nonzero') else {'all_descendant_termination':'unproven','signals':[{'signal':s,'result':'sent'} for s in ('SIGTERM','SIGKILL')],'direct_child':'unproven' if case=='injected_wait_failure' else 'reaped'}
            if case=='injected_wait_failure':cleanup['wait_error']='TimeoutExpired'
            receipt={'case':case,'reason':{'success':None,'nonzero':'failed_command','output_cap':'stopped_pipe_limit'}.get(case,'stopped_deadline'),'status':'passed' if case=='success' else 'failed','sample_count':2,'minimum_observed_free_bytes':8*1024**3,'elapsed_seconds':0.5,'fixture_identity':{'pid':123,'pgid':123,'ready':True},'all_descendant_termination':'unproven','drain_errors':[],'captured_bytes':{'stdout':len(out),'stderr':len(err)},'returncode':{'success':0,'nonzero':23,'inherited_pipe':0,'injected_wait_failure':None}.get(case,-15),'cleanup':cleanup,'truncated_pipes':['stdout'] if case=='output_cap' else []}
            if case=='injected_wait_failure':receipt['injected_wait_reconciled']=True
            self.save(leaf/'result.json',receipt)
        self.save(self.a/'example.stdout',example_fixture());(self.a/'example.stderr').write_bytes(b'')
        packages=tomllib.loads((self.w/'Cargo.lock').read_text())['package'];actual=[];nodes=[]
        for p in packages:
            ident=p['name']+'@'+p['version'];actual.append({'id':ident,'name':p['name'],'version':p['version'],'source':p.get('source')});nodes.append({'id':ident,'features':['bundled'] if p['name'] in ('rusqlite','libsqlite3-sys') else []})
        self.save(self.a/'metadata.stdout',{'packages':actual,'resolve':{'nodes':nodes}})
    def mutate(self,path,edit):p=self.a/path;data=g.load(p);edit(data);self.save(p,data)
    def reject(self):
        with self.assertRaises((ValueError,KeyError,FileNotFoundError)):v.verify(self.w,self.a)
    def test_full_positive(self):self.assertEqual(v.verify(self.w,self.a)['rust_test_total'],69)
    def test_missing_rust_name(self):
        p=self.a/'test-raw_arguments.stdout';p.write_text('\n'.join(p.read_text().splitlines()[1:]));self.reject()
    def test_duplicate_rust_name(self):
        p=self.a/'test-wire.stdout';p.write_text(p.read_text()+p.read_text().splitlines()[0]+'\n');self.reject()
    def test_wrong_summary(self):
        p=self.a/'test-storage.stdout';p.write_text(p.read_text().replace('17 passed','18 passed'));self.reject()
    def test_filtered_case(self):
        p=self.a/'test-bounds.stdout';p.write_text(p.read_text().replace('0 filtered','1 filtered'));self.reject()
    def test_partial_equal_source_maps(self):
        for name in ('source-before.json','source-after.json'):self.mutate(name,lambda d:d.pop('correction-memory/src/lib.rs'))
        self.reject()
    def test_changed_dependency_source(self):(self.w.parent/'evidence-spans/Cargo.toml').write_text('changed');self.reject()
    def test_changed_lock(self):(self.w/'Cargo.lock').write_text('changed');self.reject()
    def test_wrong_command(self):self.mutate('commands.json',lambda d:d[7]['argv'].append('--unlocked'));self.reject()
    def test_boolean_exit_code(self):self.mutate('commands.json',lambda d:d[0].update(returncode=False));self.reject()
    def test_changed_binary(self):v.c.binaries()['module'].write_bytes(b'changed');self.reject()
    def test_forged_binary_hash(self):
        for name in ('binaries-before.json','binaries-after.json'):self.mutate(name,lambda d:d['module'].update(sha256='f'*64))
        self.reject()
    def test_extra_skipped_helper(self):
        p=self.a/'validator-controls.stderr';p.write_text(p.read_text().replace('\nOK\n',"\ntest_extra (__main__.Bundle.test_extra) ... skipped 'x'\nOK\n"));self.reject()
    def test_extra_expected_failure_helper(self):
        p=self.a/'validator-controls.stderr';p.write_text(p.read_text().replace('\nOK\n','\ntest_extra (__main__.Bundle.test_extra) ... expected failure\nOK\n'));self.reject()
    def test_missing_live_receipt(self):(self.a/'live/timeout/result.json').unlink();self.reject()
    def test_wrong_live_reason(self):self.mutate('live/timeout/result.json',lambda d:d.update(reason=None));self.reject()
    def test_wait_unreconciled(self):self.mutate('live/injected_wait_failure/result.json',lambda d:d.update(injected_wait_reconciled=False));self.reject()
    def test_missing_bundled_feature(self):self.mutate('metadata.stdout',lambda d:next(n for n in d['resolve']['nodes'] if n['id'].startswith('rusqlite@')).update(features=[]));self.reject()
    def test_changed_metadata_version(self):self.mutate('metadata.stdout',lambda d:next(p for p in d['packages'] if p['name']=='rusqlite').update(version='0.34.0'));self.reject()
    def test_missing_metadata_package(self):self.mutate('metadata.stdout',lambda d:d['packages'].pop());self.reject()
    def test_example_stderr(self):(self.a/'example.stderr').write_bytes(b'error');self.reject()
    def test_example_wrong_outcome(self):self.mutate('example.stdout',lambda d:d['conflict']['metadata'][e.KEY]['result']['outcome'].update(decision='applied'));self.reject()

if __name__=='__main__':unittest.main(verbosity=2)
