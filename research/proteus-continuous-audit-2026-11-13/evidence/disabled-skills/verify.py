import json,pathlib,sys
E=pathlib.Path(__file__).resolve().parent
main=json.loads((E/'results.json').read_text());tool=json.loads((E/'tool-probe/results.json').read_text())
order=['valid_disabled','malformed_disabled','restored_disabled']
assert [main[x]['response']['ok'] for x in order]==[True,False,True]
assert 'review/SKILL.md' in main['malformed_disabled']['response']['error']
assert 'host.context.build failed' in main['malformed_disabled']['response']['error']
def events(stage):
 return [e.get('event',{}).get('envelope',{}).get('event',{}) for e in main[stage]['events']]
assert not any('ModelRequestPrepared' in e for e in events('malformed_disabled'))
assert all(any('ModelRequestPrepared' in e for e in events(x)) for x in ['valid_disabled','restored_disabled'])
parsed={x:json.loads(tool[x]['response']['output']['text']) for x in order}
assert [parsed[x]['testing']['ok'] for x in order]==[True,False,True]
assert all(not parsed[x]['review']['ok'] for x in order)
assert 'review/SKILL.md' in parsed['malformed_disabled']['testing']['error']
assert 'not available' in parsed['valid_disabled']['review']['error']
print('Confirmed: 3 real coding turns = success/error/success; 3 real tool batches = active testing success/error/success; disabled review never executes.')
print('Confirmed: failing ordinary turn emits no ModelRequestPrepared; malformed disabled review blocks unrelated active testing.')
if '--assert-isolated' in sys.argv:
 assert main['malformed_disabled']['response']['ok'], 'Disabled local skill must not block ordinary turn context or an unrelated enabled skill'
