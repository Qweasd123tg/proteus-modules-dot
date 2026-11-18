"""Offline static metadata and UI search replay. Nothing invokes a tool or reads a live settings snapshot.
Pass a Modules/Desktop worktree or bare repo plus the actual public Core contracts and serde_json rlibs.
The optional reviewed patch is applied to a fresh, display-only copy."""
import argparse,io,itertools,json,pathlib,subprocess as sp,tempfile,hashlib,re
P=pathlib.Path;p=argparse.ArgumentParser()
for k in ('modules','desktop','serde_json_rlib','core_contracts_rlib','rustc'):p.add_argument(k,type=P)
p.add_argument('--patch',type=P)
a=p.parse_args()
def read(r,f):
 if (r/f).is_file():return (r/f).read_text()
 return sp.check_output(['git','-C',str(r),'show','HEAD:'+f],text=True)
def exact_lines(r,f,ns):
 # Restrict module reads to reviewed public declaration lines. Never compile a module or handler.
 wanted=set(ns);hi=max(wanted)
 def get(stream):return {n:line.rstrip('\n') for n,line in enumerate(itertools.islice(stream,hi),1) if n in wanted}
 if (r/f).is_file():
  with (r/f).open() as stream:return get(stream)
 with sp.Popen(['git','-C',str(r),'show','HEAD:'+f],stdout=sp.PIPE,text=True) as proc:
  try:return get(proc.stdout)
  finally:proc.stdout.close()
def piece(s,b,e):return s[s.index(b):s.index(e,s.index(b))]
def block(s,b):
 i=s.index(b);j=s.index('\n}',i)+2;return s[i:j]
def val(s):return json.loads(s.split(':',1)[1].strip().rstrip(','))
git=exact_lines(a.modules,'tool/git-tools/src/lib.rs',[32,33,52,75,76,112])
rust=exact_lines(a.modules,'tool/rust-lsp/src/lib.rs',[24,100,101,121]); assert rust[100].strip()=='"name": TOOL_NAME,'
rows=[[val(git[n]),val(git[n+1]),val(git[alias])] for n,alias in [(32,52),(75,112)]]
rows.append([json.loads(rust[24].split('=',1)[1].strip().removesuffix(';')),val(rust[101]),val(rust[121])])
assert [r[0] for r in rows]==['git_status','git_diff','lsp_diagnostics']
cat='src/settings/catalog.rs';tools='src/ui/settings/tools.rs';search='src/ui/settings/search.rs';spot='src/ui/settings/spot.rs'
with tempfile.TemporaryDirectory() as temp:
 t=P(temp)
 for f in (cat,tools):
  (t/f).parent.mkdir(parents=True,exist_ok=True);(t/f).write_text(read(a.desktop,f))
 if a.patch:
  assert hashlib.sha256(a.patch.read_bytes()).hexdigest()=='1160d6a4a0b991adfeac0b46175204ecc29fb2711cf60467b93e0ebdd681756d'
  sp.run(['git','apply','--check',str(a.patch.resolve())],cwd=t,check=True);sp.run(['git','apply',str(a.patch.resolve())],cwd=t,check=True)
 c=(t/cat).read_text();u=(t/tools).read_text();s=read(a.desktop,search);go=read(a.desktop,spot)
 assert u.count('query.matches_tool(tool)' if a.patch else 'tool_matches(tool, &self.tool_query)')==3 and 'Ничего не найдено.' in u
 if a.patch:
  assert u.count('ToolQuery::new(')==1 and '&query, cx' in u and u.count('query: &ToolQuery')==2
 else:assert 'let query = self.tool_query.to_lowercase();' in u
 assert 'if hit.page == PageId::Tools && !self.tool_query.is_empty()' in go and 'self.tool_query.clear()' in go and 'state.set_value("", window, cx)' in go
 assert 'finder.add(hit, &[&tool.description, &tool.source]);' in s
 hit=piece(s,'const LIMIT:','/// Russian names')
 dst=piece(go,'#[derive(Clone, Debug, PartialEq, Eq)]','pub(super) struct Spot')
 local='' if a.patch else block(c,'pub fn tool_matches(')
 tests=''
 if a.patch:
  local=piece(c,'pub struct ToolQuery(', '#[cfg(test)]')+'\nfn tool_matches(t:&ConfigBuilderTool,q:&str)->bool {ToolQuery::new(q).matches_tool(t)}';tests=block(c,'mod tool_search_tests {').replace('#[test]','').replace('    fn matches_all','    pub(super) fn matches_all')
 before_name='name.to_lowercase().contains(&query)'
 missing='query.matches_name(name)' if a.patch else before_name
 assert f'.filter(|name| {missing})' in u
 program=P(__file__).with_name('matrix.rs.in').read_text().replace('/*HIT*/',hit.replace('pub(super)', 'pub(crate)')).replace('/*DEST*/',dst).replace('/*LOCAL*/',local).replace('/*UNIT*/',tests).replace('/*MISS*/',('let query=ToolQuery::new(q);' if a.patch else 'let query=q.trim().to_lowercase();')+missing)
 (t/'check.rs').write_text(program);(t/'rows.json').write_text(json.dumps(rows))
 sp.run([a.rustc,'--edition=2024','--cfg',('after' if a.patch else 'before'),'-A','dead_code',str(t/'check.rs'),'--extern','serde_json='+str(a.serde_json_rlib.resolve()),'--extern','proteus_contracts='+str(a.core_contracts_rlib.resolve()),'-L','dependency='+str(a.serde_json_rlib.resolve().parent),'-L','dependency='+str(a.core_contracts_rlib.resolve().parent),'-o',str(t/'check')],check=True)
 sp.run([t/'check'],check=True)
