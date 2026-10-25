#!/usr/bin/env python3
"""Check authored CI fixtures/logs, not Core execution or receipt authenticity."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tomllib

KEY = 'proteus.example.verification'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def exact_equal(left, right):
    """JSON/TOML semantic equality without bool/int/float coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(exact_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact_equal(a, b) for a, b in zip(left, right))
    return left == right

def load(path):
    return json.loads(path.read_text())

def test_totals(path, expected):
    text = path.read_text()
    summaries = re.findall(r'^test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', text, re.M)
    require(bool(summaries), f'{path.name}: missing test summaries')
    require(all(s[0] == 'ok' and all(int(n) == 0 for n in s[2:]) for s in summaries), f'{path.name}: failed, ignored, measured or filtered tests')
    total = sum(int(s[1]) for s in summaries)
    require(total == expected, f'{path.name}: expected {expected} tests, observed {total}')
    cases = re.findall(r'^test (.+) \.\.\. ok$', text, re.M)
    require(len(cases) == expected, f'{path.name}: individual passing test count differs')
    return {'passed': total, 'failed': 0, 'ignored': 0, 'filtered': 0, 'cases': cases}

def verify(workspace: Path, artifacts: Path, workspace_log: Path, review_log: Path) -> dict:
    policy = load(artifacts / 'receipt-policy.json')
    require(exact_equal(policy, load(workspace / 'fixtures/expected-policy.json')), 'helper policy differs from expected-policy fixture')
    profile = tomllib.loads((workspace / 'profile.strict.fragment.toml').read_text())
    suite = load(workspace / 'json-contracts/fixtures/suite.json')
    require(exact_equal(profile['module_config']['tool']['verification.json_contracts'], suite), 'profile producer config differs from suite')
    hook = profile['module_config']['hook']['hermes.verify_evidence']
    require(exact_equal(hook['receipt_policy'], policy), 'profile receipt policy differs from helper')
    require(hook['on_exhaustion'] == 'error', 'profile strict exhaustion must error')
    require(policy['mode'] == 'strict_json_contracts', 'policy is not strict')
    positive_outer = load(artifacts / 'positive.json')
    negative_outer = load(artifacts / 'negative.json')
    require(positive_outer['host_kind'] == negative_outer['host_kind'] == 'synthetic_authored_fixture', 'incorrect fixture host label')
    positive, negative = positive_outer['result'], negative_outer['result']
    require(positive['ok'] is True and positive.get('error') is None, 'positive result failed')
    receipt = positive['metadata'][KEY]
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 2 and receipt['status'] == 'passed' and receipt['kind'] == 'json_contracts', 'invalid receipt schema/status/kind')
    require(receipt['verifier_call_id'] == positive['call_id'] == 'authored-example', 'verifier call ID mismatch')
    require(receipt['cwd'] == '/authored-fixture', 'receipt cwd mismatch')
    expected = policy['expected']
    require(receipt['suite_id'] == expected['expected_suite_id'] and receipt['config_sha256'] == expected['expected_config_sha256'], 'receipt policy identity mismatch')
    require(len(receipt['documents']) == len(expected['documents']) == 1, 'document count mismatch')
    document, wanted = receipt['documents'][0], expected['documents'][0]
    require(document['document_id'] == wanted['document_id'] and document['configured_path'] == wanted['path'], 'document identity mismatch')
    require(document['observed_path'] == '/authored-fixture/' + wanted['path'], 'observed document path mismatch')
    require(isinstance(document['reader_call_id'], str) and document['reader_call_id'] and document['reader_call_id'] != positive['call_id'], 'reader call ID invalid')
    content = (workspace / 'json-contracts' / wanted['path']).read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    require(document['content_sha256'] == digest, 'content digest mismatch')
    require(type(document['bytes']) is int and document['bytes'] == len(content), 'content byte count mismatch')
    actual = document['assertions_executed']
    require(len(actual) == len(wanted['assertions']) == 5, 'assertion count mismatch')
    wanted_assertions = [{**a, 'check_id': f"json:{receipt['suite_id']}:{receipt['config_sha256']}:{digest}:{wanted['document_id']}:{a['assertion_id']}"} for a in wanted['assertions']]
    require(exact_equal(sorted(actual, key=lambda a: a['assertion_id']), sorted(wanted_assertions, key=lambda a: a['assertion_id'])), 'assertion identities/check IDs mismatch')
    require(negative['ok'] is False, 'negative result unexpectedly succeeded')
    require(KEY not in (negative.get('metadata') or {}), 'negative result leaked receipt')
    require(negative['call_id'] == 'authored-example', 'negative call ID mismatch')
    require('configured JSON assertion failed: release / not-publishing' in (negative.get('error') or ''), 'negative diagnostic mismatch')
    return {'status': 'passed', 'scope': 'authored producer/gate fixtures; synthetic reader/history; no Core invocation', 'workspace_tests': test_totals(workspace_log, 81), 'independent_tests': test_totals(review_log, 8), 'policy_fixture_and_profile_match': True, 'content_and_five_assertion_identities_match': True, 'negative_has_no_receipt': True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'artifacts', 'workspace-log', 'review-log'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    # Preserve target-separated sections as well as original complete Cargo logs.
    target_dir = args.artifacts / 'targets'
    target_dir.mkdir(exist_ok=True)
    index = []
    for label, log in [('workspace', args.workspace_log), ('independent', args.review_log)]:
        sections = re.split(r'(?m)(?=^\s*(?:Running |Doc-tests ))', log.read_text())
        for number, section in enumerate(sections):
            name = f'{label}-{number:02}.log'
            (target_dir / name).write_text(section)
            index.append({'log': name, 'heading': section.splitlines()[0] if section else ''})
    (target_dir / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    report = verify(args.workspace, args.artifacts, args.workspace_log, args.review_log)
    (args.artifacts / 'fixture-controls.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if not k.endswith('_tests')}, sort_keys=True))

if __name__ == '__main__':
    main()
