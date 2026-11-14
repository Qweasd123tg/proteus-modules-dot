"""Verify intentionally inconsistent Responses terminal-output robustness fixtures."""
import pathlib,json
E=pathlib.Path(__file__).resolve().parent
rows=[]
for case in json.loads((E/'summary.json').read_text()):
 name=case['case'];assert case['provider_requests']==1
 records=[json.loads(s) for s in (E/f'{name}-journal.jsonl').read_text().splitlines()]
 outcome=[r['payload']['value']['outcome'] for r in records if r['kind']=='model_response_recorded'][0]
 usage=case['usage_response']['output']['requests'][0]
 done,shape,_=name.split('-',2)
 fail=done=='done' and shape in ['head','tail']
 assert case['responses'][0]['ok']==(not fail)
 if fail:
  assert outcome['status']=='error' and 'omitted completed model messages' in outcome['failure']['message']
  assert usage['usage'] is None and usage['finish_reason'] is None
  messages=outcome['failure']['completed_messages']
 else:
  assert outcome['status']=='response'
  messages=outcome['response']['messages'];assert usage['usage']['input_tokens']==123 and usage['usage']['output_tokens']==45
 texts=[p['payload']['Text']['text'] for m in messages for p in m['parts'] if 'Text' in p['payload']]
 assert len(texts)==(1 if done=='deltas' and shape in ['head','tail'] else 2)
 rows.append(dict(case=name,success=not fail,durable_terminal_texts=texts,usage_status=usage['status'],finish_reason=usage['finish_reason'],usage=usage['usage']))
assert len(rows)==8
(E/'analysis.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2));print('8 captured cases verified; no evidence of real-provider incidence claimed.')
