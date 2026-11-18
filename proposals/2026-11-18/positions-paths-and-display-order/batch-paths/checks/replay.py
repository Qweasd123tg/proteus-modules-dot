"""Build a pure presentation fixture from three ordinary checkouts (or bare git repositories), offline.
Reads only the shipped static descriptor, Core public ToolSpec declaration, and Desktop data/presentation source.
No tool handlers, files listed in arguments, running chat/host, clipboard or GPUI window are used."""
import argparse, pathlib, subprocess as sp,tempfile,re,json
P=pathlib.Path
p=argparse.ArgumentParser()
for k in ('modules','core','desktop','serde_json_rlib','core_contracts_rlib','rustc'):p.add_argument(k,type=P)
p.add_argument('--expect',choices=['before','after'],required=True);a=p.parse_args()
def fragment(repo,path,begin,end,keep=True):
 # Read only the required source interval. A normal worktree may contain the applied local patch.
 def segment(lines):
  it=iter(lines)
  for first in it:
   if begin in first:break
  else:raise AssertionError((path,begin))
  buf=[first]
  for line in it:
   if end in line:
    if keep:buf.append(line)
    return ''.join(buf)
   buf.append(line)
  raise AssertionError((path,end))
 full=repo/path
 if full.is_file():
  with full.open() as f:return segment(f)
 with sp.Popen(['git','-C',str(repo),'show','HEAD:'+path],stdout=sp.PIPE,text=True) as g:
  try:return segment(g.stdout)
  finally:g.stdout.close()
def fn(repo,path,begin):
 # All target functions/structs are top-level here, and each has an unindented closing brace.
 def fold(lines):
  got=False;out=[]
  for l in lines:
   if not got:got=begin in l
   if got:
    out.append(l)
    if l.rstrip() == '}':return ''.join(out)
  raise AssertionError((path,begin))
 if (repo/path).is_file():
  with (repo/path).open() as f:return fold(f)
 with sp.Popen(['git','-C',str(repo),'show','HEAD:'+path],stdout=sp.PIPE,text=True) as proc:
  try:return fold(proc.stdout)
  finally:proc.stdout.close()
# This scope stops at the end of the literal, before invoke_json.
raw=fragment(a.modules,'tool/file-tools/src/read_many.rs','let spec = json!({','});')
doc=json.loads(raw.split('json!(',1)[1].rsplit(');',1)[0]);assert doc['name']=='read_many_files'
spec=fragment(a.core,'crates/proteus-contracts/src/domain/tool.rs','pub struct ToolSpec {','}')
assert 'pub input_schema: serde_json::Value' in spec and 'pub metadata: serde_json::Value' in spec
d=a.desktop; tp='src/tool_display/mod.rs';ui='src/ui/chat/tool_row.rs'
consts=fragment(d,tp,'const SUBJECT_KEYS','const TUNING_ARGS')
klass=fn(d,tp,'fn known_subject(');obj=fn(d,tp,'pub struct Headline')
subjectfn=fn(d,tp,'pub fn headline(')
branch=subjectfn[subjectfn.index('    let key = match known'):];actual=fn(d,ui,'fn argument_details(')
assert 'tool_display::path_list_preview' in actual if a.expect=='after' else 'tool_display::path_list_preview' not in actual
assert 'tool_args(tool)' in actual and 'tool_display::headline(&tool.name, args)' in actual
assert 'details.children(argument_details(fold, tool, cx))' in fragment(d,ui,'let details = match (patch, plan)','(None, None) =>')
body='\n'.join(fn(d,tp,k) for k in ('fn subject_text(','fn single_line(','fn generic_subject_key(','fn limit(','pub fn other_args(','fn arg_preview('))
helper=fn(d,tp,'pub fn path_list_preview(') if a.expect=='after' else ''
test=fn(d,'src/tool_display/tests.rs','fn expanded_known_path_list_is_bounded') if a.expect=='after' else 'fn expanded_known_path_list_is_bounded_and_keeps_filename_boundaries() {}'
rust=P(__file__).with_name('display.rs.in').read_text()
for k,v in dict(CONSTS=consts,KNOWN=klass,HEAD=obj,BRANCH=branch,FUNCS=body,HELP=helper,TEST=test,UI=actual,TOOL_ARGS=fn(d,ui,'fn tool_args(')).items():rust=rust.replace('/*'+k+'*/',v)
with tempfile.TemporaryDirectory() as tmp:
 t=P(tmp);(t/'input.json').write_text(json.dumps(doc));(t/'check.rs').write_text(rust)
 sp.run([a.rustc,'--edition=2024','-A','dead_code','--cfg',a.expect,str(t/'check.rs'),'--extern','serde_json='+str(a.serde_json_rlib.resolve()),'--extern','proteus_contracts='+str(a.core_contracts_rlib.resolve()),'-L','dependency='+str(a.serde_json_rlib.resolve().parent),'-L','dependency='+str(a.core_contracts_rlib.resolve().parent),'-o',str(t/'check')],check=True)
 sp.run([t/'check'],check=True)
