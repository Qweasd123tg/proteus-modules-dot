"""Verify captured process results; --expect-correct is the desired invariant (red today)."""
import json, pathlib, sys
E=pathlib.Path(__file__).resolve().parent

def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values(): yield from walk(child)
    elif isinstance(value,list):
        for child in value: yield from walk(child)

summaries=json.loads((E/'summary.json').read_text())
http={x['case']:x['request'] for x in json.loads((E/'provider-requests.json').read_text())}
rows=[]
for summary in summaries:
    name=summary['case']; assert summary['responses'][0]['ok'], summary
    assert summary['provider_requests']==1
    events=json.loads((E/f'{name}-events.json').read_text())
    snapshots=[v['TokenUsageUpdated']['usage'] for v in walk(events) if 'TokenUsageUpdated' in v]
    assert len(snapshots)==1
    snapshot=snapshots[0]
    records=[json.loads(line) for line in (E/f'{name}-journal.jsonl').read_text().splitlines()]
    raw=[r['payload']['value'] for r in records if r['kind']=='model_request_recorded'];assert len(raw)==1
    request=raw[0]['request'];instructions=request['instructions']
    instruction_bytes=sum(len(i['text'].encode()) for i in instructions)
    http_instruction_bytes=len(http[name].get('instructions','').encode()); assert instruction_bytes==http_instruction_bytes
    expected_instructions=(instruction_bytes+8*len(instructions))//4 if instructions else 0
    emitted={x['name']:x['tokens'] for x in snapshot['categories']}.get('instructions',0)
    row=summary['usage_response']['output']['requests'][0]
    assert row['status']=='completed' and row['finish_reason']=='Stop'
    assert row['usage']==snapshot['actual']
    if 'no_usage' in name:
        assert snapshot['actual'] is None and snapshot['source']=='estimated'
    else:
        assert row['usage']['input_tokens']==123+instruction_bytes//4
        assert row['usage']['output_tokens']==45
    rows.append(dict(case=name,instructions_utf8_bytes=instruction_bytes,expected_instructions_estimate=expected_instructions,emitted_instructions_estimate=emitted,emitted_total_estimate=snapshot['estimated_input_tokens'],actual_input=None if row['usage'] is None else row['usage']['input_tokens'],usage_source=snapshot['source']))
assert len(rows)==7
by={r['case'].split('-full')[0]:r for r in rows}
assert by['none']['emitted_total_estimate']==107
assert by['codex_default']['instructions_utf8_bytes']==20903
assert by['codex_sol']['instructions_utf8_bytes']==21779
assert by['hook']['instructions_utf8_bytes']==by['inline']['instructions_utf8_bytes']==40000
assert by['hook']['emitted_total_estimate']==107
assert by['inline']['emitted_total_estimate']==10109
assert by['inline']['emitted_instructions_estimate']==10002
assert by['codex_no_usage']['emitted_total_estimate']==107
(E/'analysis.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
if '--expect-correct' in sys.argv:
    errors=[r for r in rows if r['expected_instructions_estimate']!=r['emitted_instructions_estimate']]
    assert not errors, 'BeforeModel instruction estimate omitted in: '+', '.join(r['case'] for r in errors)
print('7 captured native process cases verified; provider usage remains correct.')
