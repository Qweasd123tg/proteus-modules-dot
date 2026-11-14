"""Validate observed diagnostic behavior, or fail on desired visible-status invariant."""
import json,pathlib,sys
E=pathlib.Path(__file__).resolve().parent
records=json.loads((E/'provider-requests.json').read_text())
def provider_results(case):
    request=[r['request'] for r in records if r['case']==case][-1]
    return [p for m in request['messages'] for p in m['content'] if isinstance(p,dict) and p.get('type')=='tool_result']
def events(case,key):
    rows=json.loads((E/f'{case}-events.json').read_text())
    return [row['event']['envelope']['event'][key] for row in rows if key in row.get('event',{}).get('envelope',{}).get('event',{})]
for case in ['complete','timed_out','timed_out_repeat','partial_timeout','collaboration_timeout']:
    summaries=[r for r in json.loads((E/'summary.json').read_text()) if r['case']==case]
    assert len(summaries)==1 and summaries[0]['response']['ok'],case
    expected='completed' if case=='complete' else 'timed_out'
    assert events(case,'SubagentFinished')[-1]['status']==expected,case
    result=provider_results(case)[-1]
    if case.startswith('timed_out') or case=='partial_timeout':
        actual=events(case,'ToolFinished')[-1]['result']
        assert actual['ok'] and actual['metadata']['status']=='timed_out',actual
        assert actual['metadata']['resumable'] is False,actual
        assert result['is_error'] is False,result
        assert 'timed_out' not in result['content'] and 'timeout' not in result['content'].lower(),result
        if case=='partial_timeout': assert result['content'].startswith('Fake final answer.'),result
        else: assert result['content']=='(no output)',result
        if '--expect-visible-status' in sys.argv:
            assert result['is_error'] or 'timed_out' in result['content'],f'{case}: child timed_out hidden from model: {result}'
    elif case=='complete':
        assert 'completed its assignment.' in result['content'] and not result['is_error'],result
    else:
        status=json.loads(result['content'])
        assert status['agents'][0]['status']=='timed_out',status
        assert status['timed_out'] is False,'wait itself did not time out; child did'
    print('DIAGNOSTIC PASS',case,result)
