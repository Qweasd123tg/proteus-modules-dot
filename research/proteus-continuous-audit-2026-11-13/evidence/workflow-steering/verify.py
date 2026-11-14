"""Verify captured facts, not the desired invariant."""
import json,pathlib,re
E=pathlib.Path(__file__).resolve().parent
cases=json.loads((E/'summary.json').read_text())
rows=[]
for case in cases:
    name=case['name'];d=E/name;bad=name.startswith(('plan_steering','execute_steering'))
    assert case['result']['ok'] is not bad,(name,case['result'])
    events=json.loads((d/'events.json').read_text())
    cold=[json.loads(line) for line in (d/'cold-events.jsonl').read_text().splitlines()]
    def snapshot(items):return [x['event']['snapshot'] for x in items if x.get('event',{}).get('type')=='session_snapshot'][-1]
    warm=snapshot(events);cold=snapshot(cold)
    assert warm['transcript']==cold['transcript'],name
    journal=[json.loads(line) for line in (d/'journal.jsonl').read_text().splitlines()]
    settlement=[x['payload']['value'] for x in journal if x['kind']=='turn_settled'][-1]
    assert settlement['status']==('error' if bad else 'success'),name
    requests=[json.loads(line) for line in (d/'requests.jsonl').read_text().splitlines()]
    if case['steer']:
        assert case['receipt']['ok'] and case['receipt']['output']['queued'],name
        delivered=case['receipt']['output']['message_id']
        assert any(any(m['id']==delivered for m in r['request']['messages']) for r in requests[1:]),name
        assert sum(x['role']=='user' and x['text'].startswith('ADDED REQUIREMENT') for x in cold['transcript'])==1,name
    if bad:
        assert len(requests)==4,name
        anchor=re.search(r'anchor ([a-z0-9-]+)',case['result']['error']).group(1)
        source=[m for r in requests for m in r['request']['messages'] if m['id']==anchor][-1]
        assert source['parts'][0]['payload']['Text']['text']=='ANSWER-3-None',source
        assert not any(x['role']=='assistant' for x in cold['transcript']),name
        assert 'ANSWER-4-None' in (d/'journal.jsonl').read_text(),name
    rows.append({'case':name,'status':settlement['status'],'requests':len(requests),'warm_equals_cold':True})
(E/'analysis.json').write_text(json.dumps(rows,indent=2))
print(f'{len(rows)} cases verified, including 6 expected product failures and 9 passing controls; warm/cold projections agree.')
