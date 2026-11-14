#!/usr/bin/env python3
import json, subprocess, pathlib
root=pathlib.Path('/workspace/scratch/3ba0fff8d310/protocol-extensions')
def config(mode):
    return {'session_settings':[{'id':'mode','control':{'type':'select','value':mode,'options':[{'value':'plan','name':'PLAN'},{'value':'auto','name':'AUTO'}]}}]}
messages=[
 {'type':'hello','protocol':4,'workspace':'/fixture','server':{'origin':'http://127.0.0.1:1','token':'synthetic'},'features':['session.settings.v1']},
 {'type':'context','context':'source','workspace':'/one','session_dir':'/one'},
 {'type':'session_snapshot','context':'source','session_dir':'/one','state':{'config':config('plan')},'entries':[]},
 {'type':'render','context':'source','view':'source-badge','surface':'badge','session_dir':'/one'},
 {'type':'render','context':'source','view':'source-picker','surface':'popup','session_dir':'/one'},
 {'type':'context','context':'sibling','workspace':'/one','session_dir':'/one'},
 {'type':'render','context':'sibling','view':'sibling-badge','surface':'badge','session_dir':'/one'},
 {'type':'action','view':'source-picker','action':'mode','value':'auto','sequence':1},
 # Mode requests close_popup; keep its composer badge alive, as Desktop does.
 {'type':'close','view':'source-picker'},
 # The source window changes chats while the real HTTP operation is in flight.
 {'type':'context','context':'source','workspace':'/two','session_dir':'/two'},
 {'type':'command_result','context':'source','id':'setting-1','session_dir':'/one','config':config('auto'),'error':None},
 # A normal render of the still-open sibling window must display server-confirmed mode.
 {'type':'render','context':'sibling','view':'sibling-badge','surface':'badge','session_dir':'/one'},
]
proc=subprocess.run([root/'target/debug/mode'],input=''.join(json.dumps(m)+'\n' for m in messages),capture_output=True,text=True,timeout=5)
assert proc.returncode==0,proc.stderr
output=[json.loads(s) for s in proc.stdout.splitlines()]
badges=[m for m in output if m.get('view')=='sibling-badge']
report={'exit_code':proc.returncode,'sibling_labels':[m['face']['text'] for m in badges], 'expected_final_label':'AUTO','actual_final_label':badges[-1]['face']['text'],'request':[m for m in output if m['type']=='set_session']}
print(json.dumps(report,indent=2))
pathlib.Path('/workspace/shared/protocol-audit-evidence/mode-wire-transcript.json').write_text(json.dumps({'input':messages,'output':output,'stderr':proc.stderr},indent=2))
assert badges[-1]['face']['text']=='AUTO','server confirmed AUTO, but live sibling reverted to PLAN'
