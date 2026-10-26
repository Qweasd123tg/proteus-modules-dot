"""Copied generic typed/named/live evidence checks; not product runtime proof."""
from collections import Counter
import ast
import hashlib
import json
from pathlib import Path
import re
def require(value, message):
    if not value: raise ValueError(message)


def exact(a, b):
    if type(a) is not type(b): return False
    if isinstance(a, dict): return a.keys() == b.keys() and all(exact(a[k], b[k]) for k in a)
    if isinstance(a, list): return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    return a == b


def pairs(items):
    out = {}
    for k, v in items:
        require(k not in out, 'duplicate JSON key'); out[k] = v
    return out


def load(path):
    return json.loads(path.read_text(), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def tests(text, names):
    require(len(names) > 0 and len(names) == len(set(names)), 'invalid expected names')
    found = re.findall(r'^test (.+) \.\.\. ok$', text, re.M)
    require(Counter(found) == Counter(names), 'named test set mismatch')
    summaries = re.findall(r'^test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out;', text, re.M)
    require(summaries == [('ok', str(len(names)), '0', '0', '0', '0')], 'exact target summary mismatch')
    require(not re.search(r'^test .+ \.\.\. (?!ok$)', text, re.M), 'nonpassed test')
    return {'count': len(names), 'names': sorted(found)}


def python_names(path):
    tree=ast.parse(path.read_text())
    return sorted((f.name,cls.name) for cls in tree.body if isinstance(cls,ast.ClassDef)
                  for f in cls.body if isinstance(f,ast.FunctionDef) and f.name.startswith('test_'))


def helper(text, path):
    expected=python_names(path)
    found=re.findall(r'^(test_\w+) \(__main__\.(\w+)\.(test_\w+)\) \.\.\. (.+)$', text, re.M)
    require(len(found)==len(re.findall(r'^test_.*$',text,re.M)), 'unparsed helper row')
    require(all(a==b and status=='ok' for a,_,b,status in found), 'helper identity/status')
    require(Counter((a,cls) for a,cls,_,_ in found)==Counter(expected), 'helper exact names')
    require(re.findall(r'^Ran (\d+) tests in [0-9.]+s$',text,re.M)==[str(len(expected))], 'helper summary')
    require(text.rstrip().endswith('\nOK') and not re.search(r'^(FAILED|ERROR:|FAIL:)',text,re.M), 'helper failure')
    return len(expected)


def live_receipts(artifacts):
    cases=['success','nonzero','timeout','output_cap','inherited_pipe','injected_wait_failure']
    live=load(artifacts/'live/summary.json')
    require(live['status']=='passed' and exact(live['count'],6) and live['cases']==cases, 'live summary')
    for case in cases:
        leaf=artifacts/'live'/case; receipt=load(leaf/'result.json')
        reason={'success':None,'nonzero':'failed_command','output_cap':'stopped_pipe_limit'}.get(case,'stopped_deadline')
        require(receipt['case']==case and receipt['reason']==reason, 'live reason/case')
        require(receipt['status']==('passed' if case=='success' else 'failed'), 'live status')
        require(type(receipt['sample_count']) is int and receipt['sample_count']>0, 'live samples')
        require(type(receipt['minimum_observed_free_bytes']) is int and receipt['minimum_observed_free_bytes']>=1024**3+128*1024**2, 'live disk')
        require(type(receipt['elapsed_seconds']) in (float,int) and 0<=receipt['elapsed_seconds']<=7, 'live clock')
        ident=receipt['fixture_identity']
        require(type(ident['pid']) is int and ident['pid']>0 and exact(ident['pgid'],ident['pid']) and ident['ready'] is True, 'live readiness identity')
        require(receipt['all_descendant_termination']=='unproven' and receipt['drain_errors']==[], 'live scope/errors')
        for stream in ('stdout','stderr'):
            size=(leaf/(stream+'.bin')).stat().st_size
            require(type(receipt['captured_bytes'][stream]) is int and receipt['captured_bytes'][stream]==size<=4096, 'live capture')
        if case=='success':
            require(exact(receipt['returncode'],0) and receipt['cleanup'] is None, 'live success exit')
            require((leaf/'stdout.bin').read_bytes()==b'fixture-ok\n' and (leaf/'stderr.bin').read_bytes()==b'', 'live success bytes')
        elif case=='nonzero':
            require(exact(receipt['returncode'],23) and receipt['cleanup'] is None, 'live nonzero exit')
            require((leaf/'stderr.bin').read_bytes()==b'fixture-nonzero\n' and (leaf/'stdout.bin').read_bytes()==b'', 'live nonzero bytes')
        else:
            cleanup=receipt['cleanup']; require(cleanup['all_descendant_termination']=='unproven', 'cleanup scope')
            require([x['signal'] for x in cleanup['signals']]==['SIGTERM','SIGKILL'], 'cleanup signals')
            require(all(x['result'] in ('sent','group_absent') for x in cleanup['signals']), 'cleanup signal error')
            if case=='injected_wait_failure':
                require(cleanup['direct_child']=='unproven' and cleanup['wait_error']=='TimeoutExpired' and receipt['returncode'] is None and receipt['injected_wait_reconciled'] is True, 'injected wait reconciliation')
            else:
                require(cleanup['direct_child']=='reaped' and type(receipt['returncode']) is int, 'live direct reap')
                require(receipt['returncode']==0 if case=='inherited_pipe' else receipt['returncode'] in (-15,-9), 'live exit signal')
        require(receipt['truncated_pipes']==(['stdout'] if case=='output_cap' else []), 'live truncation')
        if case=='output_cap': require((leaf/'stdout.bin').read_bytes()==b'x'*4096, 'live exact output cap')
    return live

