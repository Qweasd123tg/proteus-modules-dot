#!/usr/bin/env python3
"""Independent SYNTHETIC artifact-gate controls. No Core, subprocess or Rust run.

Fixtures exercise the observer's selected JSON fields; they are not journals
accepted by Core and must never be counted as actual host/settlement evidence.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ARGS = argparse.ArgumentParser()
ARGS.add_argument('--package', type=Path, required=True)
OPT, REST = ARGS.parse_known_args()
PACKAGE = OPT.package.resolve()
SPEC = importlib.util.spec_from_file_location('owned_host_gate', PACKAGE / 'verify_host.py')
G = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)


def load(path):
    return json.loads(path.read_text())


def put(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def fixture(root, case):
    directory = root / case
    directory.mkdir()
    workspace = directory / 'workspace'
    workspace.mkdir()
    cwd = str(workspace)
    content = (PACKAGE / 'fixtures/release.json').read_bytes()
    file = workspace / 'fixtures/release.json'
    approved = case != 'approval_denied'
    if case not in ('approval_denied', 'default_deny'):
        file.parent.mkdir()
        file.write_bytes(content)
    identity = {'execution_id': '11111111-1111-4111-8111-111111111111',
                'thread_id': '22222222-2222-4222-8222-222222222222',
                'turn_id': '33333333-3333-4333-8333-333333333333'}
    write = {'id': G.WRITE, 'name': 'write_file',
             'args': {'path': 'fixtures/release.json', 'content': content.decode()},
             'surface': 'function', 'raw_arguments': None}
    def result(call_id, ok=True, error=None, output='', metadata=None):
        return {'call_id': call_id, 'ok': ok, 'error': error, 'output': output,
                'content': [], 'metadata': metadata}
    if case == 'default_deny':
        reason = "policy deny_all rejects tool 'write_file'"
        denial = result(G.WRITE, False, reason)
        attribution = {'execution_id': identity['execution_id'], 'agent': None}
        records = [{'phase': 'requested', 'attribution': attribution, 'call': write},
                   {'phase': 'resolved', 'attribution': attribution, 'call': write,
                    'resolution': {'decision': 'policy_denied', 'reason': reason}},
                   {'phase': 'result', 'attribution': attribution, 'result': denial}]
        put(directory / 'report.json', {'scenario': case, 'scope': 'direct_admission_not_turn',
            'cwd': cwd, 'facts': {'approvals': [], 'result': denial, 'records': records}})
        return directory
    compiled = load(PACKAGE / 'fixtures/expected-policy.json')
    effective = deepcopy(compiled)
    if case == 'wrong_suite': effective['expected']['expected_suite_id'] = 'different-suite'
    if case == 'wrong_config': effective['expected']['expected_config_sha256'] = '0' * 64
    if case == 'missing_assertion':
        effective['expected']['documents'][0]['assertions'].append({'assertion_id': 'extra-required', 'pointer': '/extra'})
    put(directory / 'config.json', {'module_config': {
        'tool': {'verification.json_contracts': load(PACKAGE / 'fixtures/suite.json')},
        'hook': {'hermes.verify_evidence': {'receipt_policy': effective}}}})
    records = []
    def record(kind, payload, history=False):
        item = {'schema_version': 21, 'session_seq': len(records) + 1,
                'session_id': '44444444-4444-4444-8444-444444444444',
                'record_id': f'55555555-5555-4555-8555-{len(records):012d}',
                **identity, 'entry': {'kind': kind, 'payload': payload}}
        if history: item['execution_id'] = None
        records.append(item)
        return item
    record('turn_opened', {'base_history_revision': 0, 'config_snapshot': {
        'schema_version': 8,
        'modules': {'workflow': 'coding.single_loop', 'context': 'simple',
                    'policy': 'smoke.strict_policy', 'hooks': ['hermes.verify_evidence']},
        'active_provider': 'smoke.strict_scripted',
        'model': {'provider': 'smoke.strict_scripted', 'model': 'smoke.strict_scripted'},
        'approval_available': True, 'permission_mode_default': 'normal',
        'agent_control_surface': 'none',
        'tools': [{'spec': {'name': name}} for name in
                  ('read_file', 'verification.json_contracts', 'write_file')]}})
    record('history_mutated', {'previous_revision': 0, 'new_revision': 1}, True)
    model_count = 3 if case in ('matching', 'omitted', 'approval_denied') else 4
    for index in range(model_count):
        exchange = f'exchange-{index}'
        record('model_request_recorded', {'exchange_id': exchange})
        record('model_response_recorded', {'exchange_id': exchange, 'outcome': {'status': 'response'}})
    def phase(call, value):
        return record('tool_call_recorded', {'call': deepcopy(call), 'phase': value})
    def end(call_id, terminal):
        record('tool_effect_recorded', {'result': deepcopy(terminal)})
        record('tool_result_recorded', {'result': deepcopy(terminal)})
    phase(write, {'phase': 'requested', 'owner': {'owner': 'workflow'}})
    phase(write, {'phase': 'approval_requested', 'reason': 'exact authored write'})
    resolution = {'decision': 'approved'} if approved else {
        'decision': 'approval_denied', 'reason': 'strict fixture approval deliberately denied'}
    phase(write, {'phase': 'resolved', 'resolution': resolution})
    wr = result(G.WRITE, approved, None if approved else resolution['reason'])
    end(G.WRITE, wr)
    outer_results = [wr]
    receipt_checks = []
    if case not in ('omitted', 'approval_denied'):
        verifier = {'id': G.VERIFY, 'name': 'verification.json_contracts', 'args': {}}
        reader = {'id': 'reader-one', 'name': 'read_file', 'args': {'path': 'fixtures/release.json'}}
        phase(verifier, {'phase': 'requested', 'owner': {'owner': 'workflow'}})
        phase(verifier, {'phase': 'resolved', 'resolution': {'decision': 'allowed'}})
        phase(reader, {'phase': 'requested', 'owner': {'owner': 'tool', 'call_id': G.VERIFY}})
        denied = case == 'read_denied'
        rr = {'decision': 'policy_denied', 'reason': 'strict fixture read deliberately denied'} if denied else {'decision': 'allowed'}
        phase(reader, {'phase': 'resolved', 'resolution': rr})
        read_result = result('reader-one', not denied, rr.get('reason'), '' if denied else content.decode())
        end('reader-one', read_result)
        if denied:
            vr = result(G.VERIFY, False, 'host read_file failed: strict fixture read deliberately denied')
        else:
            expected = compiled['expected']
            document = expected['documents'][0]
            content_hash = hashlib.sha256(content).hexdigest()
            receipt = {'schema_version': 2, 'status': 'passed', 'kind': 'json_contracts',
                'cwd': cwd, 'verifier_call_id': G.VERIFY, 'suite_id': expected['expected_suite_id'],
                'config_sha256': expected['expected_config_sha256'], 'documents': [{
                    'document_id': document['document_id'], 'configured_path': document['path'],
                    'observed_path': cwd + '/' + document['path'], 'reader_call_id': 'reader-one',
                    'content_sha256': content_hash, 'bytes': len(content), 'assertions_executed': [
                        dict(a, check_id=f"json:{expected['expected_suite_id']}:{expected['expected_config_sha256']}:{content_hash}:{document['document_id']}:{a['assertion_id']}")
                        for a in document['assertions']]}]}
            vr = result(G.VERIFY, metadata={G.KEY: receipt})
            errors = {'matching': None, 'wrong_suite': 'receipt suite mismatch',
                      'wrong_config': 'receipt config digest mismatch',
                      'missing_assertion': 'receipt assertion coverage mismatch'}
            receipt_checks = [{'status': 'valid', 'receipt': deepcopy(receipt), 'effective_policy_error': errors[case]}]
        end(G.VERIFY, vr)
        outer_results.append(vr)
    history = [{'id': f'message-{i}', 'role': 'Tool', 'tool_call_id': r['call_id'], 'parts': [{
        'part_id': f'part-{i}', 'provenance': 'tool', 'scope': 'conversation',
        'payload': {'ToolResult': {'result': deepcopy(r)}}}]} for i, r in enumerate(outer_results)]
    success = case == 'matching'
    for attempt in range(1 if success else 2):
        accepted = success or attempt == 0
        outcome = {'status': 'accepted', 'response': {'action': 'continue' if success else 'continue_turn'}} if accepted else {'status': 'failed', 'message': G.ERROR}
        record('hook_invoked', {'input': {'event': {'event': 'before_stop', 'attempt': attempt,
            'continuation': None, 'history': deepcopy(history)}},
            'steps': [{'module_id': 'hermes.verify_evidence', 'outcome': outcome}],
            'output': {'continuation': None if success else 'Verification evidence is missing'} if accepted else None})
    record('history_mutated', {'previous_revision': 1, 'new_revision': 2}, True)
    record('turn_settled', {'status': 'success' if success else 'error',
        'output': {'text': 'candidate'} if success else None, 'error': None if success else G.ERROR}, True)
    report = {'scenario': case, 'scope': 'actual_agent_runtime_turn', 'cwd': cwd,
        'session_id': records[0]['session_id'], 'original_compiled_policy': compiled,
        'effective_gate_policy': effective, 'outcome': {'status': 'success' if success else 'error', 'error': None if success else G.ERROR},
        'approvals': [{'exact_match': True, 'approved': approved, 'cache': 'none',
                       'origin': identity, 'call': write, 'cwd': cwd}],
        'receipt_checks': receipt_checks, 'observed_content': content.decode() if approved else None}
    projection = {'history': deepcopy(history), **{n: [] for n in (
        'interrupted_turns', 'interrupted_model_exchanges', 'interrupted_context_builds', 'unresolved_tool_calls', 'unsettled_turns')}}
    for name, value in [('records', records), ('history', history), ('projection', projection), ('report', report)]:
        put(directory / (name + '.json'), value)
    return directory


class GateControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='strict-host-synthetic-gate-')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def baseline(self, case='matching'):
        directory = fixture(self.root, case)
        self.assertEqual(G.verify(directory, PACKAGE)['status'], 'passed')
        return directory

    def reject(self, filename, change, diagnostic, case='matching'):
        directory = self.baseline(case)
        path = directory / filename
        value = load(path)
        change(value)
        put(path, value)
        with self.assertRaisesRegex(ValueError, diagnostic):
            G.verify(directory, PACKAGE)

    def test_all_eight_synthetic_baselines(self):
        for case in G.CASES:
            with self.subTest(case=case): self.baseline(case)

    def test_wrong_approval_origin(self):
        self.reject('report.json', lambda v: v['approvals'][0]['origin'].update(execution_id='other'), 'approval origin')

    def test_cached_approval(self):
        self.reject('report.json', lambda v: v['approvals'][0].update(cache='session'), 'approval authority')

    def test_missing_actual_written_file(self):
        d = self.baseline()
        (d / 'workspace/fixtures/release.json').unlink()
        with self.assertRaisesRegex(ValueError, 'filesystem oracle'): G.verify(d, PACKAGE)

    def test_unrelated_gate_failure(self):
        self.reject('report.json', lambda v: v['outcome'].update(error='timeout'), 'strict gate exhaustion', 'wrong_suite')

    def test_effective_policy_mutation_drift(self):
        self.reject('report.json', lambda v: v['effective_gate_policy']['expected'].update(expected_suite_id='unrelated'), 'policy mutation mismatch', 'wrong_suite')

    def test_forged_execution_on_history_fact(self):
        self.reject('records.json', lambda v: v[1].update(execution_id=v[0]['execution_id']), 'attribution|execution')

    def test_unknown_execution_on_effect(self):
        self.reject('records.json', lambda v: next(r for r in v if r['entry']['kind']=='tool_effect_recorded').update(execution_id=None), 'attribution|execution')

    def test_boolean_schema_is_not_integer(self):
        self.reject('records.json', lambda v: v[0].update(schema_version=True), 'schema')

    def test_float_sequence_is_not_integer(self):
        self.reject('records.json', lambda v: v[0].update(session_seq=1.0), 'sequential|sequence')

    def test_duplicate_json_key(self):
        d = self.baseline()
        p = d / 'report.json'
        p.write_text(p.read_text().replace('"scenario": "matching"', '"scenario": "matching", "scenario": "matching"', 1))
        with self.assertRaisesRegex(ValueError, 'duplicate'): G.verify(d, PACKAGE)

    def test_default_deny_unrelated_error(self):
        self.reject('report.json', lambda v: v['facts']['result'].update(error='timeout'), 'default-deny result', 'default_deny')

    def test_default_deny_wrong_recorded_call(self):
        self.reject('report.json', lambda v: v['facts']['records'][0]['call'].update(name='other_tool'), 'default-deny recorded exact call', 'default_deny')

    def test_default_deny_wrong_recorded_args(self):
        self.reject('report.json', lambda v: v['facts']['records'][1]['call']['args'].update(path='other.json'), 'default-deny recorded exact call', 'default_deny')

    def test_default_deny_divergent_final_result(self):
        self.reject('report.json', lambda v: v['facts']['records'][2]['result'].update(output='other'), 'default-deny recorded final result', 'default_deny')

    def test_default_deny_divergent_execution(self):
        self.reject('report.json', lambda v: v['facts']['records'][1]['attribution'].update(execution_id='other'), 'default-deny detached execution', 'default_deny')

    def test_read_denial_not_permission_failure_elsewhere(self):
        def change(v):
            next(r for r in v if r['entry']['kind']=='tool_result_recorded' and r['entry']['payload']['result']['call_id']=='reader-one')['entry']['payload']['result']['error']='unrelated error'
        self.reject('records.json', change, 'reader denial diagnostic', 'read_denied')

    def test_wrong_nested_owner(self):
        def change(v):
            next(r for r in v if r['entry']['kind']=='tool_call_recorded' and r['entry']['payload']['call']['id']=='reader-one' and r['entry']['payload']['phase']['phase']=='requested')['entry']['payload']['phase']['owner']['call_id']='other-verifier'
        self.reject('records.json', change, 'nested read ownership')

    def test_canonical_result_divergence(self):
        d = self.baseline()
        history = load(d / 'history.json')
        history[0]['parts'][0]['payload']['ToolResult']['result']['output']='changed after final journal'
        put(d / 'history.json', history)
        projection = load(d / 'projection.json'); projection['history'] = history; put(d / 'projection.json', projection)
        with self.assertRaisesRegex(ValueError, 'canonical.*final|final.*canonical'): G.verify(d, PACKAGE)

    def test_lowercase_role_rejected(self):
        d = self.baseline()
        history = load(d / 'history.json');history[0]['role']='tool';put(d / 'history.json',history)
        p=load(d / 'projection.json');p['history']=history;put(d / 'projection.json',p)
        with self.assertRaisesRegex(ValueError,'provenance'):G.verify(d,PACKAGE)

    def test_bool_attempt_rejected(self):
        def change(v):
            next(r for r in v if r['entry']['kind']=='hook_invoked')['entry']['payload']['input']['event']['attempt']=False
        self.reject('records.json',change,'attempt')

    def test_forged_execution_on_settlement(self):
        self.reject('records.json', lambda v: v[-1].update(execution_id=v[0]['execution_id']), 'attribution|execution')

    def test_duplicate_model_exchange(self):
        def change(v):
            for kind in ('model_request_recorded','model_response_recorded'):
                matches=[r for r in v if r['entry']['kind']==kind]
                matches[1]['entry']['payload']['exchange_id']=matches[0]['entry']['payload']['exchange_id']
        self.reject('records.json',change,'exchange')

    def test_response_before_request(self):
        def change(v):
            a=next(i for i,r in enumerate(v) if r['entry']['kind']=='model_request_recorded')
            b=next(i for i,r in enumerate(v) if r['entry']['kind']=='model_response_recorded')
            v[a],v[b]=v[b],v[a]
            for i,r in enumerate(v,1):r['session_seq']=i
        self.reject('records.json',change,'exchange|request.*response|response.*request')

    def test_response_after_settlement(self):
        def change(v):
            i=next(i for i,r in enumerate(v) if r['entry']['kind']=='model_response_recorded')
            v.append(v.pop(i))
            for i,r in enumerate(v,1):r['session_seq']=i
        self.reject('records.json',change,'settle|last|boundar')

    def test_raw_result_after_final(self):
        def change(v):
            a=next(i for i,r in enumerate(v) if r['entry']['kind']=='tool_effect_recorded')
            b=next(i for i,r in enumerate(v) if r['entry']['kind']=='tool_result_recorded')
            v[a],v[b]=v[b],v[a]
            for i,r in enumerate(v,1):r['session_seq']=i
        self.reject('records.json',change,'raw/final ordering')


    def test_actual_snapshot_schema_exact_int(self):
        self.reject('records.json', lambda v: v[0]['entry']['payload']['config_snapshot'].update(schema_version=8.0), 'actual config snapshot schema')

    def test_actual_module_assembly_wrong_hook(self):
        self.reject('records.json', lambda v: v[0]['entry']['payload']['config_snapshot']['modules'].update(hooks=[]), 'actual module assembly')

    def test_actual_model_binding_wrong_provider(self):
        self.reject('records.json', lambda v: v[0]['entry']['payload']['config_snapshot']['model'].update(provider='other'), 'actual scripted model binding')

    def test_actual_approval_boolean_not_integer(self):
        self.reject('records.json', lambda v: v[0]['entry']['payload']['config_snapshot'].update(approval_available=1), 'actual runtime authority mode')

    def test_actual_registry_extra_tool(self):
        self.reject('records.json', lambda v: v[0]['entry']['payload']['config_snapshot']['tools'].append({'spec': {'name': 'shell'}}), 'actual registered tool set')


class CaptureControls(unittest.TestCase):
    """Invented process metadata only; no executable, child or signal is used."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='strict-capture-synthetic-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        names = ('host', 'official', 'fixture', 'producer', 'gate', 'policy')
        self.inputs = {name: {'path': '/authored-unexecuted/' + name, 'sha256': 'a' * 64} for name in names}
        put(self.root / 'inputs-before.json', self.inputs)
        put(self.root / 'inputs-after.json', self.inputs)
        self.processes = []
        for index, case in enumerate(G.CASES, 1):
            d = self.root / case; d.mkdir()
            original = Path('/authored-unexecuted/cases') / case
            put(d / 'report.json', {'cwd': str(original / 'workspace')})
            for stream in ('stdout', 'stderr'): (self.root / (case + '.' + stream)).write_bytes(b'')
            self.processes.append({'scenario': case,
                'command': [self.inputs['host']['path'], case, str(original), *[self.inputs[n]['path'] for n in names[1:]]],
                'cwd': str(original.parent / (case + '-environment')),
                'returncode': 0, 'timed_out': False, 'root_pid': index,
                'owned_processes': [{'direct_popen_child': True, 'pid': index, 'start_time': 100}],
                'capture_error': None, 'cleanup_error': None, 'inspection_errors': [],
                'remaining_owned_children': [], 'disk_guard_stopped': False,
                'direct_child_cleanup_fallback': False, 'minimum_observed_free_bytes': 4 * 1024**3,
                'disk_stop_bytes': 1024**3 + 128 * 1024**2, 'disk_reserve_bytes': 1024**3,
                'limits': {'cpu_seconds': 60, 'address_space_bytes': 1024**3, 'file_bytes': 8 * 1024**2,
                           'wall_seconds': 60, 'cleanup_seconds': 5.2},
                'wall_seconds': 1.0,
                'stdout_sha256': hashlib.sha256(b'').hexdigest(), 'stderr_sha256': hashlib.sha256(b'').hexdigest()})
        put(self.root / 'processes.json', self.processes)
        self.assertEqual(G.verify_capture(self.root)['status'], 'passed')

    def reject(self, change, diagnostic):
        change(self.processes)
        put(self.root / 'processes.json', self.processes)
        with self.assertRaisesRegex(ValueError, diagnostic): G.verify_capture(self.root)

    def test_complete_synthetic_capture_baseline(self):
        self.assertEqual(G.verify_capture(self.root)['scenarios'], list(G.CASES))

    def test_capture_input_hash_drift(self):
        self.inputs['host']['sha256'] = 'b' * 64
        put(self.root / 'inputs-after.json', self.inputs)
        with self.assertRaisesRegex(ValueError, 'input hashes changed'): G.verify_capture(self.root)

    def test_capture_missing_case(self):
        self.reject(lambda p: p.pop(), 'scenario order/count')

    def test_capture_wrong_command(self):
        self.reject(lambda p: p[0]['command'].__setitem__(0, '/other-host'), 'command/input')

    def test_capture_wrong_environment(self):
        self.reject(lambda p: p[0].update(cwd='/other-environment'), 'isolated environment')

    def test_capture_boolean_exit(self):
        self.reject(lambda p: p[0].update(returncode=False), 'did not complete successfully')

    def test_capture_boolean_root_identity(self):
        self.reject(lambda p: p[0]['owned_processes'][0].update(pid=True), 'direct child identity mismatch')

    def test_capture_timeout(self):
        self.reject(lambda p: p[0].update(timed_out=True), 'did not complete successfully')

    def test_capture_unknown_cleanup(self):
        self.reject(lambda p: p[0].update(remaining_owned_children=None), 'cleanup not proved')

    def test_capture_inspection_error(self):
        self.reject(lambda p: p[0].update(inspection_errors=['authored unavailable child list']), 'cleanup not proved')

    def test_capture_direct_fallback(self):
        self.reject(lambda p: p[0].update(direct_child_cleanup_fallback=True), 'failure fallback/guard')

    def test_capture_disk_guard_stopped(self):
        self.reject(lambda p: p[0].update(disk_guard_stopped=True), 'failure fallback/guard')

    def test_capture_disk_reserve_crossed(self):
        self.reject(lambda p: p[0].update(minimum_observed_free_bytes=1024**3-1), 'disk reserve crossed')

    def test_capture_changed_resource_budget(self):
        self.reject(lambda p: p[0]['limits'].update(wall_seconds=600), 'resource limits mismatch')

    def test_capture_wall_bound(self):
        self.reject(lambda p: p[0].update(wall_seconds=66), 'wall bound mismatch')

    def test_capture_output_changed(self):
        (self.root / (G.CASES[0] + '.stdout')).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'output digest mismatch'): G.verify_capture(self.root)


if __name__ == '__main__':
    unittest.main(argv=[__file__, *REST], verbosity=2)
