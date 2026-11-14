"""Diagnostic assertions pass on the observed bug. --expect-budgeted must fail."""
import json, pathlib, sys
E=pathlib.Path(__file__).resolve().parent
rows=json.loads((E/'summary.json').read_text())
expected={'output-hook-False':200000,'output-hook-True':16000,'text-hook-False':300000,'text-hook-True':300000,'json-hook-False':300011,'json-hook-True':300011,'error-hook-False':200000,'error-hook-True':200000,'preferred_output-hook-False':20,'preferred_output-hook-True':20}
assert len(rows)==len(expected)
for row in rows:
    name=row['case']
    assert row['response']['ok'] is True, (name,row['response'])
    assert row['provider_requests']==2
    assert row['provider_tool_text_bytes']==[expected[name]], row
    events=json.loads((E/f'{name}-events.json').read_text())
    results=[x['event']['envelope']['event']['ToolFinished']['result'] for x in events if 'ToolFinished' in x.get('event',{}).get('envelope',{}).get('event',{})]
    assert len(results)==1,(name,len(results))
    result=results[0]
    if row['mode'] in ('text','json'):
        assert result['output']==''
        assert not result['metadata'].get('output_truncated',False)
        assert not result['metadata'].get('error_truncated',False)
        assert len(result['content'])==1
    if row['mode']=='output':
        assert result['metadata']['output_truncated'] is True
        assert result['metadata']['output_original_bytes']==300000
    if '--expect-budgeted' in sys.argv:
        limit=16000 if row['hook'] else 200000
        assert row['provider_tool_text_bytes'][0] <= limit, f"{name}: provider receives {row['provider_tool_text_bytes'][0]} > {limit} bytes"
print('PASS: ten real-chain diagnostic scenarios; structured content bypass reproduced.')
