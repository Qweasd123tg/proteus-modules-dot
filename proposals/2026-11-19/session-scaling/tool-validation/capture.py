import json, sys, pathlib,re
# Extract static spec JSON literals (no general Rust parser; fails on other expressions).
root=pathlib.Path(sys.argv[1]); paths=[*[(root/'tool/file-tools/src').joinpath(n+'.rs') for n in ('read','write','edit','list','search','find','read_many')],root/'tool/git-tools/src/lib.rs']
specs=[]
for p in paths:
 s=p.read_text()
 for lit in re.findall(r'fn spec_json\(&self\) -> String \{.*?json!\((\{.*?\})\);',s,flags=re.S):
  if p.name=='lib.rs':
   assert 'const TIMEOUT_MS: u64 = 60_000;' in s
   lit=lit.replace(': TIMEOUT_MS',': 60000')
  for name,secs in re.findall(r'const (\w+_TIMEOUT): Duration = Duration::from_secs\((\d+)\);',s):
   lit=lit.replace(name+'.as_millis() as u64', str(int(secs)*1000))
  specs.append(json.loads(lit))
assert len(specs)==9, len(specs)
print(json.dumps(specs,ensure_ascii=False,indent=2))
