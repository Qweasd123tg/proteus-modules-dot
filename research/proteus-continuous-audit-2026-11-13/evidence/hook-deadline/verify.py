"""Validate captured process traces; --expect-consistent is intentionally red on current HEAD."""
import collections, json, pathlib, sys
E=pathlib.Path(__file__).resolve().parent
summaries={s['case']:s for s in json.loads((E/'summary.json').read_text())}
expected={
 'none':(True,1),'noop':(True,1),'slow_before_model':(False,0),
 'slow_before_context':(True,1),'slow_before_model_no_model_timeout':(True,1),
 'slow_before_model_turn_timeout':(False,0),'fast_provider':(True,1),'slow_provider':(False,1),
 'aux_one_fast':(True,2),'aux_two_fast':(False,2),'aux_two_fast_no_model_timeout':(True,3),
}
records=json.loads((E/'provider-requests.json').read_text());analysis=[]
for name,(ok,count) in expected.items():
 s=summaries[name];r=s['responses'][0];assert r['ok']==ok,(name,r)
 assert s['provider_requests']==count==(sum(v['case']==name for v in records)),(name,count)
 hooks=[json.loads(x) for x in (E/f'{name}-hook.jsonl').read_text().splitlines()]
 starts=[x['time'] for x in hooks if x['phase']=='before_model' and x['point']=='start']
 ends=[x['time'] for x in hooks if x['phase']=='before_model' and x['point']=='end']
 cancels=[x['time'] for x in hooks if x['phase']=='before_model' and x['point']=='cancel']
 duration=(ends[0]-starts[0] if starts and ends else None)
 reqs=s['usage_response']['output']['requests'];aux=[x for x in reqs if x['origin']=='auxiliary']
 direct=[x for x in reqs if x['origin']=='direct']
 journal=[json.loads(x) for x in (E/f'{name}-journal.jsonl').read_text().splitlines()]
 assert all(x['payload']['storage']=='inline' for x in journal)
 settled=[x['payload']['value']['status'] for x in journal if x['kind']=='turn_settled']
 assert settled==[('success' if ok else 'timeout' if name=='slow_before_model_turn_timeout' else 'error')],(name,settled)
 assert len(reqs)==sum(x['kind']=='model_request_recorded' for x in journal)
 assert all(x['status']=='completed' and x['usage']['input_tokens']==123 and x['usage']['output_tokens']==45 for x in aux)
 if name in ['slow_before_model','aux_two_fast']:
  assert r['error']=='model request timed out after 400ms';assert not cancels
  assert duration>.4;assert len(direct)==1 and direct[0]['status']=='error'
 if name=='slow_before_model_turn_timeout':assert cancels and not ends and not reqs
 if name=='aux_two_fast':
  assert len(aux)==2
  assert all(x['finished_at_ms']-x['started_at_ms']<400 for x in aux)
 if name=='slow_before_model':assert duration>1.1
 analysis.append({'case':name,'turn_seconds':s['elapsed'],'before_model_seconds':duration,'before_model_canceled':bool(cancels),'ok':ok,'error':r.get('error'),'http_requests':count,'usage_direct':[{'status':x['status'],'duration_ms':x['finished_at_ms']-x['started_at_ms']} for x in direct],'usage_auxiliary':[{'status':x['status'],'duration_ms':x['finished_at_ms']-x['started_at_ms']} for x in aux]})
(E/'analysis.json').write_text(json.dumps(analysis,indent=2))
print(f'PASS: {len(expected)} complete process scenarios, {len(records)} loopback HTTP requests; provider usage preserved for auxiliary calls.')
if '--expect-consistent' in sys.argv:
 row=next(x for x in analysis if x['case']=='slow_before_model')
 assert row['ok'] or row['before_model_canceled'], 'BeforeModel consumed 1.2 seconds without receiving model cancellation, then the untouched provider was rejected for a 400ms model timeout: choose and consistently enforce one deadline scope.'
