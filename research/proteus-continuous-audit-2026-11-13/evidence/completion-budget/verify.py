"""Diagnostic assertions for cross-agent splice. --expect-complete must fail."""
import json, pathlib, sys
E=pathlib.Path(__file__).resolve().parent
rows=json.loads((E/'summary.json').read_text())
requests=json.loads((E/'provider-requests.json').read_text())
report=[]
for row in rows:
    case=row['case']; count=row['count']; cid=f'call_step_{count}'
    assert row['response']['ok'] and row['terminal_count']==count,row
    assert row['second_wait']=={'timed_out':True,'agents':[]},row
    assert row['listed_agents']==count and not row['list_has_payload'],row
    req=[r['request'] for r in requests if r['case']==case][-1]
    blocks={x['tool_use_id']:x for m in req['messages'] for x in m['content'] if x.get('type')=='tool_result'}
    delivered=blocks[cid]
    assert not delivered['is_error']
    events=json.loads((E/f'{case}-events.json').read_text())
    tool=[v['event']['envelope']['event']['ToolFinished']['result'] for v in events if v.get('event',{}).get('envelope',{}).get('event',{}).get('ToolFinished',{}).get('result',{}).get('call_id')==cid][0]
    assert tool['output']==delivered['content'] and tool['ok']
    journal_rows=[]
    for p in (E/f'{case}-sessions').rglob('journal.jsonl'):
        candidate=[json.loads(l) for l in p.read_text().splitlines()]
        if any(r['kind']=='tool_result_recorded' for r in candidate):journal_rows=candidate;root_journal=p;break
    assert journal_rows,case
    for r in journal_rows:
        if r['payload']['storage']=='blob':
            r['payload']['value']=json.loads((root_journal.parent/r['payload']['relative_path']).read_text())
    def result(kind):
        return [r['payload']['value']['result'] for r in journal_rows if r['kind']==kind and r['payload'].get('value',{}).get('result',{}).get('call_id')==cid]
    assert result('tool_result_recorded')[0]['output']==delivered['content']
    assert [r['payload']['value']['status'] for r in journal_rows if r['kind']=='turn_settled']==['success']
    if row['hook']:
        raw=result('tool_effect_recorded')[0]
        raw_batch=json.loads(raw['output'])
        assert len(raw_batch['agents'])==count
        assert all(a['summary'].startswith(f"UNIQUE_WORKER_{i}_REPORT") and a['summary'].endswith(f"UNIQUE_WORKER_{i}_REPORT") for i,a in enumerate(raw_batch['agents']))
    if case in ('six-hook','six-hook-repeat'):
        batch=json.loads(delivered['content'])
        assert len(batch['agents'])==2
        assert batch['agents'][1]['path']=='/root/worker_1'
        mixed=batch['agents'][1]['summary']
        assert mixed.startswith('UNIQUE_WORKER_1_REPORT') and mixed.endswith('UNIQUE_WORKER_5_REPORT')
        assert all(f'UNIQUE_WORKER_{i}_REPORT' not in delivered['content'] for i in [2,3,4])
        assert not tool['metadata'].get('output_truncated',False)
        assert 'truncat' not in delivered['content'].lower()
        report.append({'case':case,'root_journal':str(root_journal.relative_to(E)),'raw_bytes':len(raw['output'].encode()),'raw_agents':len(raw_batch['agents']),'visible_bytes':len(delivered['content'].encode()),'visible_agents':len(batch['agents']),'corrupt_record':{'path':batch['agents'][1]['path'],'summary_head':mixed[:50],'summary_tail':mixed[-50:]},'metadata':tool['metadata']})
        if '--expect-complete' in sys.argv:
            assert len(batch['agents'])==count, f'{case}: wait consumed {count}, model received {len(batch["agents"])}; worker_1 contains worker_5 tail'
    elif case=='escaped-core-cap':
        assert tool['metadata']['output_truncated'] and len(tool['output'].encode())==200000
        try:json.loads(delivered['content'])
        except json.JSONDecodeError:pass
        else:raise AssertionError('diagnostic malformed JSON not reproduced')
    else:
        batch=json.loads(delivered['content'])
        assert len(batch['agents'])==count
        assert all(a['summary'].startswith(f"UNIQUE_WORKER_{i}_REPORT") and a['summary'].endswith(f"UNIQUE_WORKER_{i}_REPORT") for i,a in enumerate(batch['agents']))
    print('DIAGNOSTIC PASS',case)
(E/'journal-summary.json').write_text(json.dumps(report,indent=2))
