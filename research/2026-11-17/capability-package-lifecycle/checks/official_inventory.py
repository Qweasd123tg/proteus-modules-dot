"""Read-only cross-catalog check; no scripts/components are built, loaded or launched."""
import collections,json,pathlib,subprocess as sp,sys
modules,extensions,desktop,core=sys.argv[1:]
M='0fe8e3b4dfb64ca2e07df8af016d7ccc3a7de45f'; E='ef064381d2194d95faef2b85f6cc3a1c34c6b975'; D='2307e9c67125bbe66f15ced51317a2dfcc437aa4'; C='c2cbadee518788f306ffb2b5271036b2658ea8cc'
def read(repo,rev,path):return sp.check_output(['git','-C',repo,'show',rev+':'+path],text=True)
def obj(repo,rev,path):return json.loads(read(repo,rev,path))
pin=obj(desktop,D,'repositories.json'); assert [pin[k]['rev'] for k in ['modules','extensions','harness']]==[M,E,C]
def catalog(repo,rev,path='proteus-catalog.json'):return {x['id']:x for x in obj(repo,rev,path)['entries']}
mods=catalog(modules,M); ext=catalog(extensions,E); sample=catalog(desktop,D,'examples/catalog/proteus-catalog.json')
print('Desktop repositories.json pins the exact Modules, Extensions and Core revisions checked')
print('Modules',len(mods),dict(collections.Counter(x['kind'] for x in mods.values())))
for name,alias in [('memory-pack','jsonl_memory'),('sqlite-memory','sqlite_memory')]:
 entry=mods[name];exports=obj(modules,M,entry['path']+'/exports.json')
 assert exports=={'tool':[alias],'context_provider':[alias]}
 assert entry['source']['artifact']==f'dist/{name}.zip'
 print(name,entry['version'],entry['source']['artifact'],exports)
assert 'remember_fact' in next(s for s in read(core,C,'examples/configs/proteus.example.toml').splitlines() if s.startswith('enabled = [') and 'remember_fact' in s)
assert '[components.memory-pack.exports.tool.jsonl_memory]' in read(core,C,'examples/configs/proteus.example.toml')
# Pure declaration in plan spec; do not inspect invocation.
plan_decl=sp.run(['git','-C',modules,'grep','-n','"name": "update_plan"',M,'--','tool/plan-tool/src/lib.rs'],stdout=sp.PIPE,check=True,text=True).stdout
assert ':23:' in plan_decl
assert obj(modules,M,mods['plan-tool']['path']+'/exports.json')=={'tool':['plan_tool']}
manifests={k:obj(extensions,E,en['path']+'/extension.json') for k,en in ext.items()}; assert all(man['id']==k for k,man in manifests.items())
p=manifests['plan'];assert ext['plan']['kind']=='client_extension' and p['dependencies']['tools']==['update_plan'] and 'activity' in p['surfaces']
print('Plan producer/consumer: plan-tool -> tool/plan_tool -> update_plan <- plan.dependencies.tools; artifacts',mods['plan-tool']['source']['artifact'],ext['plan']['source']['artifact'])
public_memory_names={'memory','memory-pack','sqlite-memory','jsonl_memory','sqlite_memory','remember_fact','recall_memory'}
dep={k:v.get('dependencies',{}).get('tools',[]) for k,v in manifests.items()}
hits={k:n for k,n in dep.items() if public_memory_names.intersection(n)}
print('Production Desktop manifests',len(manifests),dict(collections.Counter(x['kind'] for x in ext.values())))
print('Every manifest tool dependency:',json.dumps(dep,ensure_ascii=False,sort_keys=True)); print('Explicit memory-tool dependencies:',hits)
named=[k for k,m in manifests.items() if ('memory' in k.casefold() or 'памят' in m['title'].casefold() or 'memory' in m['title'].casefold())]
print('Dedicated memory package ID/title candidates:',named);assert not hits and not named
print('Published example catalog (not production):',[(k,v['kind']) for k,v in sample.items()])
schema=read(desktop,D,'src/catalog/schema.rs')
kind=schema.partition('pub enum Kind {')[2].partition('}')[0]
fields=schema.partition('pub struct Entry {')[2].partition('\n}')[0]
assert set(k.strip().strip(',') for k in kind.strip().splitlines())=={'ProcessModule','ClientExtension','AgentPlugin','Skill','McpServer'}
assert 'pub kind: Kind,' in fields and not any('pub '+field+':' in fields for field in ('bundle','children','members','requires'))
print('Catalog Entry: one typed kind; five recognized kinds; no bundle/member field in selected revision')
