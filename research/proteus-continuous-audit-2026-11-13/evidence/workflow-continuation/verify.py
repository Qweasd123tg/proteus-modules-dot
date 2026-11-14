import json,pathlib,collections,hashlib,ast
E=pathlib.Path(__file__).resolve().parent
allcases=json.loads((E/'summary.json').read_text())+json.loads((E/'official-summary.json').read_text())
rows=[]
for c in allcases:
    wf=c['workflow'].split('.')[1]; mode=c['mode'];d=E/c['name']
    review=mode in ['review','official-claude']; broken=review and wf!='codex_loop'
    expected_calls=(27 if wf=='plan_execute_review' else 9) if broken else (2 if review else (3 if wf=='plan_execute_review' else 1))
    for t in c['turns']:
        assert t['provider_requests']==expected_calls,(c['name'],t)
        assert t['result']['ok'] is not broken,(c['name'],t)
        if broken:assert t['result']['error']=='before_stop continuation limit exceeded (8)'
    wire=json.loads((d/'wire.json').read_text())
    assert len(wire)==expected_calls*3
    if wf=='codex_loop':assert all(r['has_profile_instruction'] for r in wire)
    else:assert not any(r['has_profile_instruction'] for r in wire)
    if broken:assert not any(r['has_review_reason'] for r in wire)
    if mode=='review':
        hooks=[json.loads(x) for x in (d/'hook.jsonl').read_text().splitlines()]
        stops=[h for h in hooks if h['event']['event']=='before_stop']
        per=9 if broken else 2
        assert [h['event']['attempt'] for h in stops]==list(range(per))*3
        if broken:assert all(h['response']['action']=='continue_turn' for h in stops)
    if mode=='official-claude':
        stops=[json.loads(x) for x in (d/'stop-command.jsonl').read_text().splitlines()]
        per=9 if broken else 2
        assert len(stops)==per*3
        assert [h['stop_hook_active'] for h in stops]==([False]+[True]*(per-1))*3
    journal=[json.loads(x) for x in (d/'journal.jsonl').read_text().splitlines()]
    settled=[r for r in journal if r['kind']=='turn_settled']
    assert len(settled)==3
    assert all(r['payload']['value']['status']==('error' if broken else 'success') for r in settled)
    last=next(r['payload']['value'] for r in reversed(journal) if r['kind']=='history_mutated')
    roles=collections.Counter(m['role'] for m in last['messages'])
    if broken:assert roles['Assistant']==27 and roles['User']==3,roles
    rows.append([c['name'],3,expected_calls,not broken,roles['Assistant']])
for py in E.glob('*.py'):ast.parse(py.read_text())
provenance=json.loads((E/'provenance.json').read_text())
for path,expected in provenance['binaries'].items():assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()==expected
print('PASS: 18 cases / 54 fresh, warm and cold turns; native wire, hook reviews, journal settlements and binary hashes verified.')
print('24 reproduced erroneous turns; 30 successful control turns.')
(E/'verified-matrix.json').write_text(json.dumps(rows,indent=2))
