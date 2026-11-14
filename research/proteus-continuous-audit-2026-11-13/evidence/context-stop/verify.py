"""Assert observed regression and controls without needing running services."""
import json, pathlib, sys
root=pathlib.Path(__file__).resolve().parent
cases=json.loads((root/'summary.json').read_text())
requests=json.loads((root/'provider-requests.json').read_text())
assert len(cases)==10
assert len(requests)==22
for case in cases:
    name=case['case'];responses=case['responses']
    reqs=[r['request'] for r in requests if r['case']==name]
    assert all(r['max_tokens']==64000 for r in reqs)
    journal=[json.loads(line) for line in (root/(name+'-journal.jsonl')).read_text().splitlines()]
    failed=[j['payload']['value']['outcome']['failure'] for j in journal if j['kind']=='model_response_recorded' and j['payload']['value']['outcome']['status']=='error']
    usage=case['usage_response'];assert usage['ok']
    usage_errors=[r for r in usage['output']['requests'] if r['status']=='error']
    assert len(usage_errors)==len(failed)
    assert all(r['usage'] is None and r['finish_reason'] is None for r in usage_errors)
    if name.startswith('compact-end_turn'):
        assert [r['ok'] for r in responses]==[True,True]
        assert len(reqs)==3 and reqs[1]!=reqs[2]
        assert not failed
    elif name.startswith('compact-'):
        assert [r['ok'] for r in responses]==[True,False]
        assert len(reqs)==3 and reqs[1]==reqs[2]
        assert len(failed)==2 and all(f['kind']=='other' for f in failed)
        assert 'length limit' in responses[-1]['error']
        if '--expect-context-recovery' in sys.argv and 'model_context_window_exceeded' in name:
            assert responses[-1]['ok'], 'REGRESSION: context-window stop retries identical summary and fails'
    else:
        assert [r['ok'] for r in responses]==[False]
        assert len(reqs)==1 and len(failed)==1 and failed[0]['kind']=='other'
    print('VERIFIED',name)
print('10 real process scenarios; 22 local provider requests; both streaming modes.')
