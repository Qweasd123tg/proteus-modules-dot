#!/usr/bin/env python3
"""python replay.py DESKTOP_TREE BEFORE_HTML AFTER_HTML RUSTC LIBMARKDOWN DEPENDENCY_DIR.
DESKTOP_TREE is a checkout, or the pinned Desktop bare repo. Uses only inert tables.
Native production functions, stdlib fixture HTML tree adapter. No browser, GPUI, clipboard or Cargo.
"""
from pathlib import Path
from html.parser import HTMLParser
import itertools,re,subprocess,sys,tempfile
desktop,base,cand,rustc,md,deps=map(Path,sys.argv[1:]);here=Path(__file__).resolve().parent
def original(file):
 p=desktop/file
 return p.read_text() if p.exists() else subprocess.check_output(['git','--git-dir='+str(desktop),'show','2307e9c:'+file],text=True)
def inside(s,key):
 i=s.index(key);b=s.rfind('\n',0,i)+1;sp=re.match(r'\s*',s[b:]).group();return s[b:s.index('\n'+sp+'}',i)+len(sp)+2]
node=original('vendor/gpui-base/src/text/node.rs')
def executable(source,d,tag,mdlib=False):
 inp=d/(tag+'.rs');out=d/tag;inp.write_text(source)
 flags=['--extern','markdown='+str(md),'-L','dependency='+str(deps)] if mdlib else []
 subprocess.run([str(rustc),'--edition=2024','-Awarnings',str(inp),'-o',str(out)]+flags,check=True);return out
class Nodes(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
 def handle_starttag(self,name,attrs):
  if name=='tr':self.row=[];self.rows.append(self.row)
  if name in ('th','td'):self.cell=[name,attrs,''];self.row.append(self.cell)
 def handle_endtag(self,name):
  if name in ('th','td'):self.cell=None
  if name=='tr':self.row=None
 def handle_data(self,d):
  if self.cell is not None:self.cell[2]+=d
def stream(rows):
 return ';'.join('/'.join('~'.join([name,','.join(k+'='+v for k,v in attrs),v]) for name,attrs,v in row) for row in rows)
def generate():
 pre={}; left={'N':'---','L':':---','C':':---:','R':'---:'}
 for n in range(1,5):
  for g in itertools.product('NLCR',repeat=n):
   for depth in [0,1,3]:
    rows=[['Название','מחיר','السعر','Цена'][:n],[left[x] for x in g]]+[list(map(str,range(ix*10,ix*10+n))) for ix in range(depth)]
    s='\n'.join('| '+' | '.join(row)+' |' for row in rows)
    pre[s]=(''.join(g),depth)
 # GFM fills missing slots and ignores extra cells. The oracle expects the
 # delimiter-column count, never inferred from the first data row.
 for body in ['12', '12 | |', '12 | 34 | 56 | extra', '12 | 34 | 56\n| 1 |']:
  pre['| כמות | | בדיקה |\n| ---: | :---: | --- |\n| '+body+' |']=('RCN',1)
 return pre
controls=[
 '<table><tr><td align="right">A</td></tr><tr><td align="right">4</td></tr></table>',
 '<table><tr><th align="right">A</th></tr><tr><td align="left">4</td></tr></table>',
 '<table><tr><th align="right">A</th></tr><tr><td>4</td></tr></table>',
 '<table><tr><th align="right">A</th></tr><tr><td colspan="2">4</td></tr></table>',
 '<table><tr><th align="right">A</th><th>B</th></tr><tr><td align="right">4</td></tr></table>',
 '<table><tr><th style="text-align:right">A</th></tr><tr><td style="text-align:right">4</td></tr></table>',
 '<table><tr><th align="right">A</th></tr><tr><th align="right">4</th></tr></table>',
 '<table><tr><th align="right">A</th></tr><tr><td align="right" width="4">4</td></tr></table>',
 '<table><tr><th>מחיר</th></tr><tr><td>12</td></tr></table>',
]
def consumer(html):
 s=(here/'frame.rs.in').read_text()
 for key,val in [('HINT',(inside(html,'fn gfm_cell_align(') if 'fn gfm_cell_align(' in html else '')),('ROW',inside(html,'fn parse_table_row(')),('ALIGN',inside(node,'fn column_align(&self,')),('MARKDOWN',inside(node,'pub(crate) fn to_markdown(&self) -> String {\n        let mut lines:')),('SELECT',inside(node,'fn table_selected_source('))]:
  s=s.replace('__'+key+'__',val)
 # actual rendering decision: numerical, not screen coordinates
 a=node[node.index('let (lead, trail) = match align {'):];a=a[:a.index('};')+2];s=s.replace('__SLACK__',a)
 assert '.when(align == ColumnumnAlign::Right, |this| this.text_right())' in node
 return s
with tempfile.TemporaryDirectory() as t:
 d=Path(t); gen=executable('use std::io::Read;fn main(){let mut s=String::new();std::io::stdin().read_to_string(&mut s).unwrap();for (i,m) in s.split(char::from(30)).enumerate(){if i>0{print!("{}", char::from(30))}print!("{}",markdown::to_html_with_options(m,&markdown::Options::gfm()).unwrap());}}',d,'producer',True)
 fixtures=generate(); sep=chr(30)
 htmls=subprocess.run([gen],input=sep.join(fixtures),capture_output=True,text=True,check=True).stdout.split(sep)
 allrows=[]
 for h in htmls+controls:
  p=Nodes();p.feed(h);assert p.rows;allrows.append(p.rows)
 sep_for={'N':':--','L':':--','C':':-:','R':'--:'}
 for state,path in [('before',base),('after',cand)]:
  native=executable(consumer(path.read_text()),d,state)
  results=subprocess.run([native],input='\n'.join(map(stream,allrows))+'\n',capture_output=True,text=True,check=True).stdout.splitlines()
  assert len(results)==len(allrows)
  bad=[0]*3; controls_bad=0
  for i,(res,rows) in enumerate(zip(results,allrows)):
   # align glyphs, whole-source separator, multi-cell selected-source separator (single selected cell has no separator), cell count.
   actual,whole,section,slack,cellcount=res.split('\t');assert int(cellcount)==sum(map(len,rows))
   if i<len(fixtures):
    expect=list(fixtures.values())[i][0]
    separator='| '+' | '.join(sep_for[c] for c in expect)+' |'
    native_slack=''.join('C' if c=='C' else 'R' if c=='R' else 'L' for c in expect)
    bad[0]+=int(slack!=native_slack); bad[1]+=int(whole!=separator)
    bad[2]+=int(section!=(separator if sum(bool(v.strip()) for r in rows for _,_,v in r)>1 else '-'))
    if state=='after': assert actual==expect
   else:controls_bad+=int(actual!='N'*len(rows[0]))
  print(state,'fixtures',len(fixtures),'mismatch display/whole/selected',bad,'generic controls',len(controls),'mismatches',controls_bad)
  assert controls_bad==0
  if state=='after':assert bad==[0]*3
