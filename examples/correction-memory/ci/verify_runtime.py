#!/usr/bin/env python3
"""Exact per-target Rust and authored-callback evidence, not real Core integration."""
import importlib.util
import json
from pathlib import Path
import sys
import tomllib

def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=module('contract');g=module('gate_common');example=module('verify_example')

def metadata(workspace,data):
    packages=tomllib.loads((workspace/'Cargo.lock').read_text())['package']
    actual=data['packages'];key=lambda p:(p['name'],p['version'],p.get('source'))
    g.require(len(actual)==len(packages)==156 and len({key(p) for p in actual})==156 and {key(p) for p in actual}=={key(p) for p in packages},'resolved package identities differ from reviewed lock')
    nodes={n['id']:n for n in data['resolve']['nodes']}
    for name,version,feature in [('rusqlite','0.33.0','bundled'),('libsqlite3-sys','0.31.0','bundled')]:
        p=[p for p in actual if p['name']==name];g.require(len(p)==1 and p[0]['version']==version and feature in nodes[p[0]['id']]['features'],'bundled SQLite resolved feature')
    return {'packages':156,'rusqlite':'0.33.0','libsqlite3-sys':'0.31.0','bundled_resolved':True,'lock_sha256':c.LOCK_SHA}

def verify(workspace,artifacts):
    before=g.load(artifacts/'source-before.json');after=g.load(artifacts/'source-after.json')
    g.require(g.exact(before,after) and g.exact(before,c.source_identity(workspace)),'source identity incomplete or changed')
    commands=g.load(artifacts/'commands.json');g.require(g.exact(commands,[{'label':label,'argv':argv,'returncode':0} for label,argv in c.plan(workspace)]),'exact fixed command sequence')
    helpers={label:g.helper((artifacts/(label+'.stderr')).read_text(),workspace/'ci'/file) for label,file in [('envelope-controls','test_envelope.py'),('validator-controls','test_runtime.py')]}
    g.require(helpers['envelope-controls']==35,'envelope control inventory')
    live=g.live_receipts(artifacts)
    expected=g.load(workspace/'ci/expected-tests.json')
    g.require(g.exact(expected['total'],69) and {k:len(v) for k,v in expected['targets'].items()}==c.TARGET_COUNTS,'exact authored target inventory')
    allnames=[n for names in expected['targets'].values() for n in names];g.require(len(set(allnames))==69,'duplicate test inventory')
    tests={name:g.tests((artifacts/('test-'+name+'.stdout')).read_text(),expected['targets'][name]) for name in c.TARGET_COUNTS}
    binaries=g.load(artifacts/'binaries-before.json');g.require(g.exact(binaries,g.load(artifacts/'binaries-after.json')) and g.exact(binaries,c.binary_identity()),'runtime binary identity')
    g.require((artifacts/'example.stderr').read_bytes()==b'','unexpected authored example stderr')
    demonstration=example.verify(g.load(artifacts/'example.stdout'))
    return {'status':'passed','rust_test_total':69,'rust_targets':tests,'separate_python_controls':helpers,'live_controls':live,'binaries':binaries,
            'metadata':metadata(workspace,g.load(artifacts/'metadata.stdout')),'example':demonstration,'actual_Core':False,'upstream_suites':False,'real_user_database':False}

if __name__=='__main__':
    result=verify(Path(sys.argv[1]),Path(sys.argv[2]));(Path(sys.argv[2])/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'rust_test_total':69,'actual_Core':False}))
