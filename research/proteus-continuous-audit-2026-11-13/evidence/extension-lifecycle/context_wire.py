#!/usr/bin/env python3
"""Real unmodified Context+SDK: replay outputs of the source-driven routing probe.
No real Desktop/Core; input SessionChanged loss is proven separately by Rust probe.
Badge-only path performs no HTTP or user-file access.
"""
import argparse,hashlib,json,pathlib,subprocess
parser=argparse.ArgumentParser();parser.add_argument('--binary',type=pathlib.Path,required=True);args=parser.parse_args()
here=pathlib.Path(__file__).resolve().parent
session='/fixture/session-new';context='fixture-window:command';view='badge@fixture'
messages=[
 {'type':'hello','protocol':4,'workspace':'/fixture/project','server':{'origin':'http://127.0.0.1:1','token':'synthetic-unused'},'features':['session.state_only.v1']},
 {'type':'context','context':context,'workspace':'/fixture/project','session_dir':session},
 {'type':'session_snapshot','context':context,'session_dir':session,'state':{'context':{'used':10,'max':100}},'entries':[]},
 {'type':'render','context':context,'view':view,'surface':'badge','session_dir':session},
 # Scope has no session subscription: state 80 is NOT delivered. Production
 # HostEvent paths still send generic events; they cannot replace state.
 {'type':'event','context':context,'session_dir':session,'event':'navigation_changed','document':None},
 {'type':'event','context':context,'session_dir':session,'event':'run_settled','document':None},
 # Control: the ordinary state update, once delivered, immediately works.
 {'type':'session_update','context':context,'session_dir':session,'update':{'type':'state','state':{'context':{'used':80,'max':100}}}},
 {'type':'event','context':context,'session_dir':session,'event':'navigation_changed','document':None},
]
run=subprocess.run([str(args.binary.resolve())],input=''.join(json.dumps(m)+'\n' for m in messages),text=True,capture_output=True,timeout=10)
assert run.returncode==0,(run.returncode,run.stderr)
assert not run.stderr,run.stderr
output=[json.loads(line) for line in run.stdout.splitlines()]
percent=[m['face']['percent'] for m in output if m.get('type')=='badge' and m.get('view')==view]
assert percent==[10.0,10.0,10.0,80.0,80.0],percent
result={'method':'real unchanged Context package/SDK, synthetic wire; native subscription event loss checked independently by Rust exact-source probe','binary_sha256':hashlib.sha256(args.binary.read_bytes()).hexdigest(),'input':messages,'output':output,'badge_percentages':percent,'stderr':run.stderr,'returncode':run.returncode,'native_desktop_run':False,'core_run':False}
(here/'context-wire.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('PASS: actual Context badge 10 -> NavigationChanged 10 -> RunSettled 10 -> forwarded state 80 -> NavigationChanged 80')
