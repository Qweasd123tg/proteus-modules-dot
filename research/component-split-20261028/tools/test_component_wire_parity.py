#!/usr/bin/env python3
"""Controller tests only: launch freshly authored Python fakes, never Rust code.

Run: python3 -m unittest discover -s tools -p test_component_wire_parity.py -v
Passing these tests is NOT real proteus-plan-module/reference-module evidence.
"""

import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest

import component_wire_parity as probe


FAKE = r'''
import json, os, signal, sys, time
mode = sys.argv[1]
if mode == 'ignore-term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
for line in sys.stdin:
    request = json.loads(line)
    if mode in ('hang', 'ignore-term'):
        time.sleep(60)
    if mode == 'reject':
        print('fixture rejection', file=sys.stderr, flush=True)
        sys.exit(1)
    if mode == 'panic':
        print('fake panic', file=sys.stderr, flush=True)
        sys.exit(101)
    if mode == 'eof-only':
        continue
    if mode == 'stderr-flood':
        os.write(2, b'x' * 100000)
        time.sleep(60)
    if mode == 'oversized':
        os.write(1, b'x' * 100000)
        time.sleep(60)
    if mode == 'frames':
        os.write(1, b'{}\n' * 100)
        time.sleep(60)
    if mode == 'malformed':
        print('{broken', flush=True)
        continue
    if mode == 'duplicate-key':
        print('{"jsonrpc":"2.0","id":"h:1:0","id":"h:1:0","result":null}', flush=True)
        continue
    if mode == 'unterminated':
        os.write(1, b'{"result":null}')
        sys.exit(0)
    if mode == 'blank':
        print('', flush=True)
        continue
    if mode == 'callback':
        response = {'jsonrpc':'2.0', 'id':'m:1:1', 'method':'host.exec', 'params':{}}
    elif mode == 'wrong-id':
        response = {'jsonrpc':'2.0', 'id':'h:9:9', 'result':None}
    elif mode == 'bad-envelope':
        response = {'jsonrpc':'2.0', 'id':request['id'], 'result':None, 'error':{}}
    elif mode == 'invalid-error':
        response = {'jsonrpc':'2.0', 'id':request['id'], 'error':{'code':True,'message':'x'}}
    elif mode in ('suite', 'suite-mismatch'):
        # Standalone fake protocol, intentionally not importing the controller.
        rid = request['id']
        if request['method'] == 'initialize':
            p = request['params']; e = p['exports'][0]
            if (rid != 'h:1:0' or p['protocol_version'] != 'v3' or
                e['slot'] != 'tool' or e['module_id'] != 'plan_tool' or
                e['contract_version'] != 'v6' or e['composition'] != 'ordered_many' or
                not isinstance(e['module_config'], dict)):
                print('fake initialize rejected', file=sys.stderr, flush=True)
                sys.exit(1)
            response = {'jsonrpc':'2.0','id':rid,'result':{
                'protocol_version':'v3','component_id':p['component_id'],'exports':[{
                    'slot':'tool','module_id':'plan_tool','contract_version':'v6',
                    'composition':'ordered_many','module_features':[], 'config_schema':{'fields':[]}}]}}
        else:
            p = request['params']
            if (not rid.startswith('h:1:') or rid == 'h:1:0' or
                p['lineage']['root_invocation_id'] != rid):
                print('fake invocation rejected', file=sys.stderr, flush=True)
                sys.exit(1)
            def error(message):
                return {'jsonrpc':'2.0','id':rid,'error':{'code':-32000,'message':message}}
            inner = p['params']
            if p['export'] != {'slot':'tool','module_id':'plan_tool'}:
                response = error('unknown export')
            elif request['method'] == 'list':
                if inner is not None:
                    response = error('tool list params must be null')
                else:
                    response = {'jsonrpc':'2.0','id':rid,'result':{'result':[{
                        'spec':{'name':'update_plan','supports_parallel_tool_calls':False,
                                'safety':'ReadOnly', 'description':'fake catalog'},
                        'model_visible':True,'user_command':None}]}}
            elif request['method'] != 'invoke':
                response = error('unknown method')
            elif 'attribution' not in inner or 'skills' not in inner:
                response = error('missing required input')
            elif inner['call']['name'] != 'update_plan':
                response = error('unknown name ' + inner['call']['name'])
            else:
                call = inner['call']; args = call['args']
                valid = (isinstance(args, dict) and 'plan' in args and
                         set(args) <= {'plan','explanation'} and
                         all(set(step) == {'step','status'} and
                             step['status'] in ('pending','in_progress','completed')
                             for step in args['plan']))
                result = {'call_id':call['id'], 'ok':valid,
                          'output':'Plan updated' if valid else '', 'content':[],
                          'error':None if valid else 'plan entries must be fake-valid', 'metadata':{}}
                if valid:
                    result['metadata'] = {'plan':args['plan'],'explanation':args.get('explanation')}
                    result['metadata'].update({s:sum(step['status']==s for step in args['plan'])
                                              for s in ('pending','in_progress','completed')})
                response = {'jsonrpc':'2.0','id':rid,'result':{'result':result}}
        if mode == 'suite-mismatch' and request['method'] == 'list' and 'result' in response:
            response['result']['result'][0]['spec']['description'] = 'changed catalog'
    else:
        response = {'jsonrpc':'2.0','id':request['id'],'result':{'echo':request['params']}}
    encoded = json.dumps(response).encode() + b'\n'
    if mode == 'chunked':
        for b in encoded:
            os.write(1, bytes([b]))
    else:
        os.write(1, encoded)
    if mode == 'trailing':
        os.write(1, encoded)
if mode == 'eof-only':
    print('only EOF caused this error', file=sys.stderr, flush=True)
    sys.exit(1)
'''


@unittest.skipUnless(os.name == "posix", "POSIX process-group tests")
class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="plan-parity-fake-")
        self.cwd = Path(self.temp.name)
        self.fake = self.cwd / "fake.py"
        self.fake.write_text(FAKE, encoding="utf-8")
        self.workers = []
        self.limits = dict(probe.LIMITS, request_seconds=0.3, cleanup_seconds=0.3,
                           frame_bytes=4096, stdout_bytes=8192, stderr_bytes=4096, frames=32)

    def tearDown(self):
        for worker in self.workers:
            worker.close()
            self.assertIsNotNone(worker.process.returncode, "direct child not reaped")
        self.temp.cleanup()

    def command(self, mode):
        return [sys.executable, str(self.fake), mode]

    def worker(self, mode, **bounds):
        worker = probe.Worker(self.command(mode), self.cwd, time.monotonic() + 5,
                              dict(self.limits, **bounds))
        self.workers.append(worker)
        return worker

    def test_chunked_frames_and_clean_eof(self):
        worker = self.worker("chunked")
        request = probe.initialize()
        response = worker.exchange(request)
        self.assertEqual(response["result"], {"echo": request["params"]})
        worker.finish()
        self.assertEqual(worker.metrics()["frames"], 1)
        self.assertEqual(worker.metrics()["stderr_bytes"], 0)

    def test_bad_responses_are_not_accepted(self):
        for mode in ("malformed", "duplicate-key", "unterminated", "blank", "callback",
                     "wrong-id", "bad-envelope", "invalid-error"):
            with self.subTest(mode=mode):
                worker = self.worker(mode)
                with self.assertRaises(probe.ProbeFailure):
                    worker.exchange(probe.initialize())
                worker.close()

    def test_finite_byte_and_frame_limits(self):
        for mode, message in (("stderr-flood", "stderr byte"), ("oversized", "byte budget"),
                              ("frames", "frame count")):
            with self.subTest(mode=mode):
                worker = self.worker(mode)
                with self.assertRaisesRegex(probe.ProbeFailure, message):
                    worker.exchange(probe.initialize())
                worker.close()

    def test_stdout_aggregate_budget_is_separate_from_frame_budget(self):
        worker = self.worker("oversized", frame_bytes=65536, stdout_bytes=1024)
        with self.assertRaisesRegex(probe.ProbeFailure, "stdout byte"):
            worker.exchange(probe.initialize())

    def test_request_count_is_bounded(self):
        worker = self.worker("chunked", frames=1)
        worker.exchange(probe.initialize())
        with self.assertRaisesRegex(probe.ProbeFailure, "request count"):
            worker.send(probe.invocation(1, "list", None))

    def test_timeout_kills_and_reaps_owned_child_even_if_term_ignored(self):
        worker = self.worker("ignore-term")
        start = time.monotonic()
        with self.assertRaises(probe.ProbeTimeout):
            worker.exchange(probe.initialize())
        worker.close()
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(worker.process.returncode, -signal.SIGKILL)

    def test_unread_stdin_has_deadline(self):
        worker = self.worker("hang", request_bytes=65536)
        worker.send(probe.initialize())
        big = probe.invocation(1, "list", "x" * 60000)
        with self.assertRaises(probe.ProbeTimeout):
            # Pipe capacity varies by OS; fill it without assuming 4/64 KiB.
            for _ in range(8):
                worker.send(big)

    def test_trailing_response_is_failure(self):
        worker = self.worker("trailing")
        worker.exchange(probe.initialize())
        with self.assertRaises(probe.ProbeFailure):
            worker.finish()

    def test_actual_rejection_passes_without_closing_stdin(self):
        worker = self.worker("reject")
        worker.send(probe.initialize())
        self.assertEqual(worker.finish(rejected=True), 1)
        self.assertFalse(worker.stdin_closed)

    def test_eof_only_failure_cannot_mask_missing_rejection(self):
        worker = self.worker("eof-only")
        worker.send(probe.initialize())
        with self.assertRaises(probe.ProbeTimeout):
            worker.finish(rejected=True)

    def test_panic_is_not_a_protocol_rejection(self):
        worker = self.worker("panic")
        worker.send(probe.initialize())
        with self.assertRaisesRegex(probe.ProbeFailure, "unexpected exit status 101"):
            worker.finish(rejected=True)

    def test_input_budget_and_suite_deadline(self):
        worker = self.worker("chunked", request_bytes=20)
        with self.assertRaisesRegex(probe.ProbeFailure, "request byte"):
            worker.send(probe.initialize())
        with self.assertRaises(probe.ProbeTimeout):
            probe.Worker(self.command("chunked"), self.cwd, time.monotonic() - 1)

    def test_full_matrix_with_independent_fake_peers(self):
        report = {}
        probe.run_suite({"reference": self.command("suite"), "candidate": self.command("suite")},
                        self.cwd, report, dict(probe.LIMITS, total_seconds=15, request_seconds=1))
        self.assertEqual(report["status"], "passed")
        self.assertEqual(len(report["scenarios"]), 13)
        self.assertTrue(all(row["status"] == "passed" for row in report["scenarios"]))
        self.assertEqual(report["scenarios"][0]["response_count"], len(probe.cases(self.cwd)) + 1)

    def test_catalog_difference_fails_with_later_scenarios_never_run(self):
        report = {}
        with self.assertRaisesRegex(probe.ProbeFailure, "transcript mismatch"):
            probe.run_suite({"reference": self.command("suite"),
                             "candidate": self.command("suite-mismatch")}, self.cwd, report,
                            dict(probe.LIMITS, total_seconds=5, request_seconds=1))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["scenarios"][0]["status"], "failed")
        self.assertTrue(all(row["status"] == "never-run" for row in report["scenarios"][1:]))

    def test_timeout_report_distinct_from_failure_and_never_run(self):
        report = {}
        with self.assertRaises(probe.ProbeTimeout):
            probe.run_suite({"reference": self.command("hang"), "candidate": self.command("suite")},
                            self.cwd, report, self.limits)
        self.assertEqual(report["status"], "timeout")
        self.assertEqual(report["scenarios"][0]["workers"]["reference"]["status"], "timeout")
        self.assertEqual(report["scenarios"][0]["workers"]["candidate"]["status"], "never-run")


class FixtureTests(unittest.TestCase):
    def test_json_nonfinite_duplicates_and_malformed_input_rejected(self):
        for raw in (b'NaN', b'Infinity', b'-Infinity', b'1e999', b'{"a":1,"a":2}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(probe.ProbeFailure):
                probe.strict_json(raw)

    def test_manifest_preserves_explicit_empty_schema(self):
        self.assertEqual(probe.manifest()["exports"][0]["config_schema"], {"fields": []})
        self.assertEqual(probe.manifest()["exports"][0]["module_features"], [])

    def test_inputs_use_pinned_required_dtos_and_raw_compatibility_cases(self):
        rows = {name: (request, expected) for name, request, expected in probe.cases(Path("/tmp"))}
        self.assertEqual(rows["raw-malformed"][1], "ok")
        raw_call = rows["raw-malformed"][0]["params"]["params"]["call"]
        self.assertEqual(raw_call["args"], {"plan": []})
        self.assertEqual(raw_call["raw_arguments"], "{not JSON")
        for name in ("missing-attribution", "missing-skills", "wrong-target-slot", "wrong-target-module_id"):
            self.assertEqual(rows[name][1], "rpc-error")
        self.assertEqual(len(rows), 22)

    def test_duplicate_definition_is_not_filtered(self):
        request = probe.invocation(1, "list", None)
        definition = {"spec": {"name": "update_plan", "supports_parallel_tool_calls": False,
                               "safety": "ReadOnly"}, "model_visible": True, "user_command": None}
        response = {"jsonrpc": "2.0", "id": request["id"], "result": {"result": [definition, definition]}}
        with self.assertRaisesRegex(probe.ProbeFailure, "exactly one"):
            probe.validate_outcome(request, response, "list")

    def test_result_call_identity_cannot_drift(self):
        request = probe.invocation(1, "invoke", probe.tool_input("empty", {"plan": []}, "/tmp"))
        value = {"call_id": "wrong", "ok": True, "output": "Plan updated", "content": [],
                 "error": None, "metadata": {}}
        response = {"jsonrpc": "2.0", "id": request["id"], "result": {"result": value}}
        with self.assertRaisesRegex(probe.ProbeFailure, "call identity"):
            probe.validate_outcome(request, response, "ok")


if __name__ == "__main__":
    unittest.main()
