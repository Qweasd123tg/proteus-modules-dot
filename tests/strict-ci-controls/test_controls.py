"""Owned synthetic controls for CI verifier only. No Rust/Cargo/product execution."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import unittest

HELPER, SOURCE, OUTPUT = map(lambda value: Path(value).resolve(), sys.argv[1:4])
del sys.argv[1:4]
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('strict_ci_verifier', HELPER)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
OUTPUT.mkdir(parents=True, exist_ok=False)
KEY = 'proteus.example.verification'

def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')

def logs(count, ignored=0):
    return ('SYNTHETIC validator-control log; no Cargo tests executed.\n' +
            ''.join(f'test authored_control_{i} ... ok\n' for i in range(count)) +
            f'test result: ok. {count} passed; 0 failed; {ignored} ignored; 0 measured; 0 filtered out; finished in 0.00s\n')

class Controls(unittest.TestCase):
    def setUp(self):
        self.root = OUTPUT / self._testMethodName
        self.workspace = self.root / 'workspace'
        self.artifacts = self.root / 'artifacts'
        self.workspace.mkdir(parents=True)
        self.artifacts.mkdir()
        for name in ['profile.strict.fragment.toml', 'fixtures/expected-policy.json',
                     'json-contracts/fixtures/suite.json', 'json-contracts/fixtures/release.json']:
            target = self.workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, target)
        self.policy = json.loads((self.workspace / 'fixtures/expected-policy.json').read_text())
        expected = self.policy['expected']
        doc = expected['documents'][0]
        content = (self.workspace / 'json-contracts' / doc['path']).read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        receipt = {'schema_version':2, 'status':'passed', 'kind':'json_contracts',
                   'cwd':'/authored-fixture', 'verifier_call_id':'authored-example',
                   'suite_id':expected['expected_suite_id'], 'config_sha256':expected['expected_config_sha256'],
                   'documents':[{'document_id':doc['document_id'], 'configured_path':doc['path'],
                     'observed_path':'/authored-fixture/' + doc['path'], 'reader_call_id':'synthetic-reader-only',
                     'content_sha256':digest, 'bytes':len(content),
                     'assertions_executed':[{**a, 'check_id':f"json:{expected['expected_suite_id']}:{expected['expected_config_sha256']}:{digest}:{doc['document_id']}:{a['assertion_id']}"} for a in doc['assertions']]}]}
        self.positive = {'host_kind':'synthetic_authored_fixture', 'result':{'call_id':'authored-example',
              'ok':True, 'error':None, 'output':'SYNTHETIC verifier-control only; no assertions executed',
              'content':[], 'metadata':{KEY:receipt}}}
        self.negative = {'host_kind':'synthetic_authored_fixture', 'result':{'call_id':'authored-example',
              'ok':False, 'error':'configured JSON assertion failed: release / not-publishing',
              'output':'', 'content':[], 'metadata':None}}
        self.wlog = self.root / 'workspace.log'
        self.rlog = self.root / 'review.log'
        self.wlog.write_text(logs(81)); self.rlog.write_text(logs(8))
        write(self.artifacts/'positive.json', self.positive)
        write(self.artifacts/'negative.json', self.negative)
        write(self.artifacts/'receipt-policy.json', self.policy)
        assert self.verify()['status'] == 'passed', 'every adversary starts from accepted synthetic control'

    def verify(self):
        return helper.verify(self.workspace, self.artifacts, self.wlog, self.rlog)

    def reject(self, diagnostic):
        with self.assertRaises(ValueError) as raised:
            self.verify()
        self.assertEqual(str(raised.exception), diagnostic)
        (self.root/'intended-rejection.txt').write_text(diagnostic+'\n')

    def save_positive(self): write(self.artifacts/'positive.json', self.positive)
    def receipt(self): return self.positive['result']['metadata'][KEY]
    def document(self): return self.receipt()['documents'][0]

    def test_positive_and_assertion_permutation(self):
        self.document()['assertions_executed'].reverse(); self.save_positive()
        report = self.verify()
        self.assertEqual(report['workspace_tests']['passed'],81)
        self.assertEqual(report['independent_tests']['passed'],8)

    def test_stale_expected_fixture_is_not_hidden_by_matching_actual_helper(self):
        policy=deepcopy(self.policy); policy['expected']['documents'][0]['assertions'][0]['pointer']='/unexecuted'
        write(self.workspace/'fixtures/expected-policy.json',policy)
        self.reject('helper policy differs from expected-policy fixture')

    def test_stale_profile_policy_is_not_hidden_by_matching_fixture(self):
        p=self.workspace/'profile.strict.fragment.toml'; text=p.read_text()
        old=self.policy['expected']['expected_config_sha256']
        self.assertEqual(text.count(f'expected_config_sha256 = "{old}"'),1)
        p.write_text(text.replace(f'expected_config_sha256 = "{old}"',f'expected_config_sha256 = "{"0"*64}"'))
        self.reject('profile receipt policy differs from helper')

    def test_profile_boolean_cannot_impersonate_numeric_expected_value(self):
        p=self.workspace/'profile.strict.fragment.toml'; text=p.read_text()
        self.assertEqual(text.count('expected = 1\n'),1)
        p.write_text(text.replace('expected = 1\n','expected = true\n'))
        self.reject('profile producer config differs from suite')

    def test_profile_float_cannot_impersonate_exact_integer_expected_value(self):
        p=self.workspace/'profile.strict.fragment.toml'; text=p.read_text()
        self.assertEqual(text.count('expected = 1\n'),1)
        p.write_text(text.replace('expected = 1\n','expected = 1.0\n'))
        self.reject('profile producer config differs from suite')

    def test_float_receipt_version_does_not_pass_integer_schema_guard(self):
        self.receipt()['schema_version']=2.0;self.save_positive()
        self.reject('invalid receipt schema/status/kind')

    def test_wrong_content_digest_even_with_consistent_check_ids(self):
        doc=self.document(); old=doc['content_sha256'];doc['content_sha256']='a'*64
        for assertion in doc['assertions_executed']: assertion['check_id']=assertion['check_id'].replace(old,doc['content_sha256'])
        self.save_positive();self.reject('content digest mismatch')

    def test_wrong_exact_content_byte_count(self):
        self.document()['bytes']+=1;self.save_positive();self.reject('content byte count mismatch')

    def test_missing_assertion_is_not_successful_partial_coverage(self):
        self.document()['assertions_executed'].pop();self.save_positive();self.reject('assertion count mismatch')

    def test_duplicate_assertion_with_same_count_is_rejected(self):
        assertions=self.document()['assertions_executed'];assertions[-1]=deepcopy(assertions[0])
        self.save_positive();self.reject('assertion identities/check IDs mismatch')

    def test_wrong_assertion_pointer_preserving_id_is_rejected(self):
        self.document()['assertions_executed'][0]['pointer']='/unexecuted';self.save_positive()
        self.reject('assertion identities/check IDs mismatch')

    def test_wrong_current_call_id(self):
        self.receipt()['verifier_call_id']='older-example';self.save_positive();self.reject('verifier call ID mismatch')

    def test_contradictory_positive_error_is_not_success(self):
        self.positive['result']['error']='synthetic failure';self.save_positive();self.reject('positive result failed')

    def test_negative_cannot_leak_a_positive_receipt(self):
        self.negative['result']['metadata']={KEY:deepcopy(self.receipt())}
        write(self.artifacts/'negative.json',self.negative);self.reject('negative result leaked receipt')

    def test_unrelated_negative_failure_is_not_expected_assertion(self):
        self.negative['result']['error']='missing file'
        write(self.artifacts/'negative.json',self.negative);self.reject('negative diagnostic mismatch')

    def test_missing_test_case_count(self):
        self.wlog.write_text(logs(80));self.reject('workspace.log: expected 81 tests, observed 80')

    def test_ignored_test_is_not_a_pass(self):
        self.rlog.write_text(logs(8,ignored=1));self.reject('review.log: failed, ignored, measured or filtered tests')

    def test_summary_without_individual_case_lines_is_not_a_pass(self):
        self.rlog.write_text('test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n')
        self.reject('review.log: individual passing test count differs')

if __name__=='__main__': unittest.main()
