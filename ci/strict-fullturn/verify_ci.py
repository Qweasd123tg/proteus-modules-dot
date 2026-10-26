#!/usr/bin/env python3
"""Exact source, prerequisite and dependency-graph gates; not host semantics."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

CORE = '3f36a003b4f3fde2242fc80f7aedac00dd127d1d'
SDK = 'bee0e409e746e2df9db32748d4f8ea02201bd4af'
MODULES = '7fceaebc3bed8add9b0e3091110f59deca86ba46'
LOCK = 'e9b46590a2ff92ded4f0934a540bbdd0e9aee83c7ebad0ac6c3bd5089b4a0848'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    require(path.is_file() and not path.is_symlink(), 'regular input required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(repo, output):
    manifest = json.loads((repo/'ci/strict-fullturn/PUBLICATION.json').read_text())
    found = {}
    for name, expected in manifest['payload_sha256'].items():
        require(not Path(name).is_absolute() and '..' not in Path(name).parts, 'unsafe input path')
        found[name] = sha(repo/name)
        require(found[name] == expected, 'source mismatch: '+name)
    output.write_text(json.dumps(found, indent=2, sort_keys=True)+'\n')


def tests(kind, log, expected):
    text = log.read_text()
    names = expected[kind]
    if kind == 'fixture':
        rows = re.findall(r'^test (\S+) \.\.\. ([^\n]+)$', text, re.M)
        require(all(status == 'ok' for _, status in rows), 'non-ok Rust test row')
        found = [name for name, _ in rows]
        summaries = re.findall(r'^test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out; finished in [^\n]+$', text, re.M)
        require(summaries == [('ok',str(len(names)),'0','0','0','0')], 'Rust count/status mismatch')
        require(len(re.findall(r'^test result:',text,re.M)) == 1, 'extra Rust result summary')
    else:
        rows = re.findall(r'^(test_\w+) \([^\n]+\) \.\.\. ([^\n]+)$', text, re.M)
        require(all(status == 'ok' for _, status in rows), 'non-ok Python test row')
        found = [name for name, _ in rows]
        require(re.findall(r'^Ran (\d+) tests in [0-9.]+s$', text, re.M) == [str(len(names))], 'Python count mismatch')
        require(text.rstrip().endswith('OK'), 'Python suite did not finish OK')
    require(sorted(found) == sorted(names), 'exact test-name mismatch: '+kind)
    require(not re.search(r'ResourceWarning|subprocess .*still running|\bskipped\b|\bFAILED\b', text), 'test warning/failure/skip')


def live(root):
    expected = {'normal': (0,False), 'nonzero': (7,False), 'timeout': (None,True),
                'detached': (None,True), 'orphan': (0,False)}
    require({p.name for p in root.iterdir()} == set(expected), 'live case set mismatch')
    for name, (rc, timeout) in expected.items():
        r = json.loads((root/name/'result.json').read_text())
        require(r['timed_out'] is timeout, 'live timeout status mismatch')
        require(type(r['returncode']) is int and (r['returncode'] == rc if rc is not None else r['returncode'] != 0), 'live exit mismatch')
        require(r['cleanup_error'] is None and r['capture_error'] is None, 'live cleanup/capture failure')
        require(r['inspection_errors'] == [] and r['remaining_owned_children'] == [], 'live descendant cleanup unknown')
        require(r['direct_child_cleanup_fallback'] is False and r['disk_guard_stopped'] is False, 'live failure fallback')
        for stream in ('stdout','stderr'):
            require(sha(root/name/stream) == r[stream+'_sha256'], 'live output identity mismatch')
        if name in ('detached','orphan'):
            require(len(r['owned_processes']) >= 2, 'descendant not observed')
        if name == 'detached':
            require(len({p['pgid'] for p in r['owned_processes']}) >= 2, 'detached group not observed')
        if name == 'orphan':
            require(bool(r['adopted_descendants']), 'orphan adoption not observed')


def graphs(output, official):
    require(sha(official/'Cargo.lock') == LOCK, 'official lock changed')
    for name in ('host','fixture','strict','official'):
        m = json.loads((output/('metadata-'+name+'.json')).read_text())
        ps = [p for p in m['packages'] if (p.get('source') or '').startswith('git+https://github.com/Proteus-harness/Proteus-core')]
        require(bool(ps), 'missing pinned Core graph: '+name)
        expected = SDK if name == 'official' else CORE
        require(all(p['source'].endswith('#'+expected) for p in ps), 'mixed Core graph: '+name)
    return {'host_fixture_strict_core':CORE, 'official_modules':MODULES, 'official_sdk':SDK, 'official_lock_sha256':LOCK}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('source','tests','live','graphs','policy'))
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--kind')
    parser.add_argument('--official',type=Path)
    args = parser.parse_args()
    expected = json.loads((args.repo/'ci/strict-fullturn/EXPECTED.json').read_text())
    if args.mode == 'source': sources(args.repo,args.output)
    elif args.mode == 'tests': tests(args.kind,args.output,expected)
    elif args.mode == 'live': live(args.output)
    elif args.mode == 'graphs': print(json.dumps(graphs(args.output,args.official),indent=2))
    elif args.mode == 'policy':
        spec=importlib.util.spec_from_file_location('strict_verifier',args.repo/'integration/strict-host/verify_host.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        require(module.same(json.loads(args.output.read_text()),json.loads((args.repo/'integration/strict-host/fixtures/expected-policy.json').read_text())), 'compiled policy differs from frozen expectation')


if __name__ == '__main__': main()
