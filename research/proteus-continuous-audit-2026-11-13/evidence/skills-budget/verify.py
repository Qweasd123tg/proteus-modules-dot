"""Diagnostic assertions. --expect-discoverable asserts the missing invariant."""
import json,sys
from pathlib import Path
E=Path(__file__).resolve().parent
results=json.loads((E/'results.json').read_text())
requests=[json.loads(line) for line in (E/'model-requests.jsonl').read_text().splitlines()]
catalogs=json.loads((E/'catalogs.json').read_text())
assert len(requests)==6,len(requests)
def chunks(r):
 return [p['payload']['Context']['chunk'] for m in r['messages'] for p in m['parts'] if 'Context' in p['payload']]
def skills(r):
 return [c for c in chunks(r) if c['metadata']['provider']=='skills']
def skill_count(r):return sum(c['content'].count('<skill>') for c in skills(r))
counts=[skill_count(r) for r in requests]
assert counts==[40,0,0,0,40,0],counts
assert all(r['response']['ok'] for r in results.values())
assert all(any(t['name']=='skill' for t in r['tools']) for r in requests)
for name,n in [('forty',40),('sixty',60)]:
 c=catalogs[name]['catalog'];assert len(c['skills'])==n and all(s['enabled'] for s in c['skills'])
 assert c['warnings']==[]
 assert all(len(s['description'])==900 for s in c['skills'])
 assert len(catalogs[name]['chunks'])==1
 assert catalogs[name]['chunks'][0]['metadata']['skill_count']==n
forty_bytes=len(catalogs['forty']['chunks'][0]['content'].encode())
sixty_bytes=len(catalogs['sixty']['chunks'][0]['content'].encode())
assert forty_bytes < 60000 < sixty_bytes
assert any(c['metadata']['provider']=='project_instructions' for c in chunks(requests[-1]))
rules_bytes=sum(len(c['content'].encode()) for c in chunks(requests[-1]) if c['metadata']['provider']=='project_instructions')
assert forty_bytes+rules_bytes > 60000
result=json.loads(results['sixty_tool']['response']['output']['text'])
assert result['ok'] and result['output']=='Synthetic workflow body 000.'
summary={'requests':len(requests),'turns':len(results),'model_visible_skill_counts':counts,'catalog_counts':{k:len(v['catalog']['skills']) for k,v in catalogs.items()},'catalog_warnings':{k:v['catalog']['warnings'] for k,v in catalogs.items()},'catalog_bytes':{'forty':forty_bytes,'sixty':sixty_bytes},'shaped_rules_bytes':rules_bytes,'default_max_context_bytes':60000,'direct_skill_tool_ok':result['ok'],'all_turns_success':True}
(E/'summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
if '--expect-discoverable' in sys.argv:
 assert skill_count(requests[1])>0,'adding valid enabled skills silently removes every skill from model context'
print('PASS: observations and controls reproduced (not a product fix).')
