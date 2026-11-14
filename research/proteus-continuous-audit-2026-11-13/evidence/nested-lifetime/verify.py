import json,pathlib,sys
E=pathlib.Path(__file__).resolve().parent
summary=lambda mode:json.loads((E/(mode+'-summary.json')).read_text())
markers=lambda mode:[json.loads(s) for s in (E/(mode+'-markers.jsonl')).read_text().splitlines()]
a=summary('clean-background');b=summary('dirty-background');c=summary('clean-wait')
for x in [a,b,c]:
 assert x['response']['ok'] is True
 assert x['reader_result'] is not None
 rs=markers(x['mode']);ready=next(y for y in rs if y['name']=='reader_ready');end=next(y for y in rs if y['name']=='before_parent_finish')
 assert ready['extra']['base_exists'] is True
 assert ready['time'] <= end['time']
 assert len([y for y in rs if y['name']=='start'])==3
 if x['mode']!='clean-wait':assert x['reader_result']['time']>=x['release_at']
assert a['reader_result']['extra']['ok'] is False
assert a['reader_result']['extra']['errno']==2
assert a['reader_result']['extra']['cwd_exists'] is False
assert 'no changes, removed' in a['response']['output']['text']
assert '[task_id:' not in a['response']['output']['text']
assert a['branches'].strip()=='* main'
assert b['reader_result']['extra']['ok'] is True
assert b['reader_result']['extra']['cwd_exists'] is True
assert '[task_id:' in b['response']['output']['text']
assert c['reader_result']['extra']['ok'] is True
assert 'no changes, removed' in c['response']['output']['text']
for mode,ok in [('identity-collision',False),('identity-unique',True)]:
 rs=markers(mode);inner=next(y for y in rs if y['name']=='task' and y['prompt'].startswith('parent-'))
 assert inner['extra']['ok'] is ok
 assert any(y['name']=='leaf_reached' for y in rs) is ok
 if not ok:assert "branch named 'proteus/next-call_0' already exists" in inner['extra']['error']
 starts=[y for y in rs if y['name']=='start'];assert len({y['session'] for y in starts})==len(starts)
 print(mode+': observed behaviour verified')
print('All five process observations and positive controls verified.')
if '--expect-fixed-lifetime' in sys.argv:
 assert a['reader_result']['extra']['ok'] is True,'cleanup removed cwd while descendant reader was still active'
if '--expect-fixed-identity' in sys.argv:
 inner=next(y for y in markers('identity-collision') if y['name']=='task' and y['prompt'].startswith('parent-'))
 assert inner['extra']['ok'] is True,'separate-session call ID collided in shared Git branch namespace'
