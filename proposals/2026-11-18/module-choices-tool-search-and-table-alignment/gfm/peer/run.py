"""ARGS: BEFORE_DESKTOP AFTER_DESKTOP EXTENSIONS MARKDOWN_RLIB SERDE_DEPS_DIR RUSTC;
optional 7th: when testing stacking, path of #197-compatible Desktop node.rs.
Only compiles source slices and expands local synthetic Markdown. lxml required."""
from pathlib import Path
import json,sys,tempfile,subprocess as sp,itertools as it
from lxml import html
b,a,e,lib,d,r=map(Path,sys.argv[1:7]);base=Path('vendor/gpui-base/src/text'); dirs=[b,a]
node=(Path(sys.argv[7]) if len(sys.argv)>7 else b/base/'node.rs').read_text()
def block(s,name):
 i=s.index(name); i2=s.index('{',i); n=1
 for j in range(i2+1,len(s)):
  if s[j]=='{':n+=1
  elif s[j]=='}':
   n-=1
   if not n:return s[i:j+1]
 raise Exception(name)
def output(exe,rows):
 inp=''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in rows)
 return [json.loads(l) for l in sp.run([exe],input=inp,text=True,stdout=sp.PIPE,check=True).stdout.splitlines()]
def compile(t,code,name,gfm=False):
 src=t/(name+'.rs');src.write_text(code);args=[str(r),'--edition=2024','-Awarnings',str(src),'-o',str(t/name),'-L','dependency='+str(d.resolve())]
 for ll in (['serde_json','anyhow'] if gfm else ['serde_json']):args.extend(['--extern',ll+'='+str(next(d.glob('lib'+ll+'-*.rlib')).resolve())])
 if gfm:args.extend(['--extern','markdown='+str(lib.resolve()),'-L','dependency='+str(lib.parent.resolve())])
 sp.run(args,check=True);return t/name
def shape(markup):
 root=html.fromstring(markup)
 if root.tag!='table':root=root.find('.//table')
 return [[(c.tag,dict(c.attrib),c.text_content()) for c in row if c.tag in ('th','td')] for row in root.xpath('./tr|./thead/tr|./tbody/tr')]
def md(cells):return '| '+' | '.join(cells)+' |'
aspec={'None':'---','Left':':---','Right':'---:','Center':':---:'}
copy={'None':':--','Left':':--','Right':'--:','Center':':-:'}
geometry={'None':[0,10],'Left':[0,10],'Center':[5,5],'Right':[10,0]}
with tempfile.TemporaryDirectory() as td:
 t=Path(td); sdk=(e/'sdk/src/ui.rs').read_text();inlines=(e/'packages/markdown-render/src/inlines.rs').read_text()
 producer=compile(t,'use serde_json::Value;use anyhow::{Result,anyhow};use std::io::{self,BufRead};mod ui{use serde_json::{Value,json};'+block(sdk,'pub fn rich_text(')+'}'+block(inlines,'fn compile(')+'fn main(){for line in io::stdin().lock().lines(){let md:String=serde_json::from_str(&line.unwrap()).unwrap();println!("{}",compile("demo",&md).unwrap())}}','produce',True)
 pairs=[]
 for n in (1,2,3):
  for align in it.product(aspec,repeat=n):
   for body in ([],[['12','','750','extra'][:n]],[['7'],['千','25','13','ignored']],[['','',''][:n],['abc','75.00','2','ignored']]):
    pairs.append((align,'\n'.join([md(['項目','€','Итог'][:n]),md([aspec[v] for v in align])]+[md(v) for v in body])+'\n'))
 docs=output(producer,[p[1] for p in pairs]);shapes=[shape(q['html']) for q in docs]
 for (align,_),q,sh in zip(pairs,docs,shapes):
  assert q['type']=='rich_text' and q['id']=='demo'
  assert all(len(row)==len(align) for row in sh)
  for i,row in enumerate(sh):
   assert all(role==('th' if i==0 else 'td') and attrs==({} if alg=='None' else {'align':alg.lower()}) for (role,attrs,val),alg in zip(row,align))
 excepts=[]
 good='<table><thead><tr><th align="right">Name</th><th align="center">Rank</th></tr></thead><tbody><tr><td align="right">A</td><td align="center">9</td></tr><tr><td align="right">B</td><td align="center">8</td></tr></tbody></table>'
 for x,y in [('<td align="right">A','<td align="left">A'),('<td align="right">B','<td width="25" align="right">B'),('<td align="center">8</td>',''),('<th align="right">Name</th>','<td align="right">Name</td>'),('<td align="right">B</td>','<th align="right">B</th>'),('<th align="right">','<th style="text-align:right">'),('<th align="center">','<th colspan="2" align="center">'),('<td align="right">A','<td align="char">A'),('<td align="right">A','<td>A')]:
  excepts.append(shape(good.replace(x,y)))
 okx=shape(good.replace('<table>','<table class="handwritten">'));control=shape('<table><tr><td>only</td></tr></table>')
 pipe=shape(good.replace('>A</td>','>red|green</td>'))
 upper_value=shape(good.replace('align="right"', 'align="RIGHT"'))
 upper_name=shape(good.replace('align=', 'ALIGN='))
 # Mixed first body and later matching rows must not re-enable the discarded hints.
 late=shape(good.replace('<td align="right">A', '<td>A').replace('</tbody>', '<tr><td align="right">Z</td><td align="center">7</td></tr></tbody>'))
 for z,path in enumerate(dirs):
  parser=(path/base/'format/html.rs').read_text();frm=Path(__file__).with_name('reader.rs.in').read_text()
  row=block(parser,'fn parse_table_row(');ha=block(parser,'fn gfm_cell_align(') if 'fn gfm_cell_align(' in parser else ''
  helper=block(node,'fn protect_table_pipes(') if 'fn protect_table_pipes(' in node else ''
  for key,s in [('HELPER',ha),('ROW',row),('COLUMN',block(node,'pub(crate) fn column_align(')),('SERIAL',block(node,'pub(crate) fn to_markdown(&self) -> String {\n        let mut lines: Vec<String> = Vec::with_capacity(self.children.len() + 1);')),('SELECT',helper+'\n'+block(node,'fn table_selected_source(')),('SLACK',block(node,'match align {\n                    ColumnumnAlign::None | ColumnumnAlign::Left => (0., grow)'))]:
   frm=frm.replace('/*'+key+'*/',s)
  obs=output(compile(t,frm,'test'+str(z)),shapes+excepts+[okx,control,pipe,upper_value,upper_name,late]); wrong=[0,0,0]
  for ((align,_),rows),(k,full,selected,geom) in zip(zip(pairs,shapes),obs):
   hdr=md([c[-1] for c in rows[0]]); src=md([copy[q] for q in align])
   assert full.splitlines()[0]==hdr;assert full.splitlines()[2:]==[md([c[-1] for c in row]) for row in rows[1:]]
   wrong[0]+=geom!=[geometry[q] for q in align];wrong[1]+=full.splitlines()[1]!=src
   if sum(bool(c[-1].strip()) for row in rows for c in row)>=2:wrong[2]+=selected.splitlines()[1]!=src
   else:assert selected==next(c[-1] for row in rows for c in row if c[-1].strip())
  assert all(o[0]==[] for o in obs[len(shapes):-6]);assert obs[-5][0]==[]
  expected_cols=(['Right','Center'] if z else [])
  assert obs[-6][0]==expected_cols and obs[-4][0]==expected_cols
  assert obs[-3][0]==[] and obs[-2][0]==expected_cols and obs[-1][0]==[]
  assert 'red\\|green' in obs[-4][1]
  assert ('red\\|green' in obs[-4][2])==('fn protect_table_pipes(' in node)
  if z:assert sum(wrong)==0
  else:assert min(wrong)>0
  print(('BEFORE','AFTER')[z],len(shapes),'GFM; absent/mismatched [geometry, full delimiter, reconstructed multi-cell delimiter]:',wrong,'; full cell counts/text preserved; 9/9 noncanonical whole-table fallbacks. Identically shaped hand-authored HTML also receives alignment.')
