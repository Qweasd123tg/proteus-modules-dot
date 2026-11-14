"""Assertions of observed defective behavior, not fixed-code regression tests."""
import json
from pathlib import Path
E=Path(__file__).resolve().parent

def load(mode):
    outputs=json.loads((E/f'{mode}-outputs.json').read_text())
    markers=[json.loads(s) for s in (E/f'{mode}-markers.jsonl').read_text().splitlines()]
    events=[v['event']['envelope'] for v in outputs if v.get('event',{}).get('type')=='runtime']
    ids={e['event']['SubagentStarted']['description']:e['event']['SubagentStarted']['child_thread_id'] for e in events if 'SubagentStarted' in e['event']}
    return outputs,markers,events,ids

o,m,e,ids=load('wait')
assert any(v['name']=='finish' and v['prompt']=='leaf' for v in m)
call=next(v['extra']['call_id'] for v in m if v['prompt']=='leaf' and v['name']=='list_agents')
forward=next(v for v in e if v['event'].get('ToolCallRequested',{}).get('call',{}).get('id')==call)
assert ids['leaf']!=ids['parent']
assert forward['thread_id']==ids['parent']
snap=[v['event']['snapshot'] for v in o if v.get('event',{}).get('type')=='session_snapshot'][-1]
parent=next(v['subagent'] for v in snap['transcript'] if (v.get('subagent') or {}).get('child_thread_id')==ids['parent'])
assert any(t['call_id']==call for t in parent['tools'])
print('PASS BGC-2: distinct leaf tool is attributed to parent, including root snapshot')

o,m,e,ids=load('background')
assert any(v['name']=='finish' and v['prompt']=='leaf' for v in m)
assert not any(v['event'].get('SubagentFinished',{}).get('child_thread_id')==ids['leaf'] for v in e)
call=next(v['extra']['call_id'] for v in m if v['prompt']=='leaf' and v['name']=='list_agents')
assert not any(v['event'].get('ToolCallRequested',{}).get('call',{}).get('id')==call for v in e)
print('PASS BGC-1: leaf finishes locally; no tool or finish reaches root after parent idle')

for mode,expected in [('ask-wait',1),('ask-background',0),('ask-background-resume',0)]:
    o,m,e,ids=load(mode)
    req=[v for v in o if v.get('event',{}).get('type')=='user_input_requested']
    assert len(req)==expected
    assert sum(v['name']=='before_user_input' for v in m)==1
    assert sum(v['name']=='after_user_input' for v in m)==expected
    if expected:
        assert any(v.get('id')=='answer' and v.get('ok') is True for v in o)
        assert req[0]['event']['request']['origin']['thread_id']==ids['parent']
    if mode.endswith('resume'):
        response=next(v for v in o if v.get('type')=='response' and v.get('id')=='resume')
        assert response['ok']
        agent=json.loads(response['output']['text'])['agents'][0]
        assert agent['generation']==2
        assert json.loads(agent['summary'])=={'timed_out':True,'agents':[]}
    print(f'PASS BGC-1 {mode}: visible user inputs={len(req)}, answered workflow={expected}')
