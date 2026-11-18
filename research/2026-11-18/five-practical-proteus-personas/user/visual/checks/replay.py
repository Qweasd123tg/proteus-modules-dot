"""Offline. ARGS: EXTENSIONS_CHECKOUT_OR_BARE, RUSTC, SERDE_JSON_AND_ANYHOW_DEP_DIR, LIBMARKDOWN_RLIB.
No network or extension processes. Prints native catalog error strings. Python, Rust 1.95, markdown-rs 1.0.0."""
from pathlib import Path
import sys,tempfile,subprocess as sp,hashlib,time,json,html.parser
e,r,d,m=map(Path,sys.argv[1:5]); here=Path(__file__).resolve().parent
p=here.parent; rev='ef064381d2194d95faef2b85f6cc3a1c34c6b975'
files={'catalog.rs':('packages/json-render/src/catalog.rs','8d4f54e6659a33a36a08ced067f3ceb8585bdb66'),'fences.rs':('packages/markdown-render/src/fences.rs','3af868c7731835b78fa95c88e568e3829614c882'),'references.rs':('packages/markdown-render/src/references.rs','e071c32a855269100a5a6c89005b4ed2479f9545')}
def src(path):
 return (e/path).read_bytes() if (e/path).exists() else sp.check_output(['git','--git-dir='+str(e),'show',rev+':'+path])
start=time.monotonic()
with tempfile.TemporaryDirectory() as td:
 t=Path(td);(t/'main.rs').write_bytes((here/'probe.rs').read_bytes());(t/'catalog').mkdir()
 for n,(path,sha) in files.items():
  code=src(path);assert hashlib.sha1(b'blob '+str(len(code)).encode()+b'\0'+code).hexdigest()==sha
  (t/n).write_bytes(code)
 (t/'catalog/svg_size.rs').write_text('pub(super) fn dimensions(_: &str)->(f64,f64){unreachable!("no SVG tests")}\n')
 argv=[r,'--edition=2024','-Awarnings',t/'main.rs','-L','dependency='+str(d),'-L','dependency='+str(m.parent),'--extern','markdown='+str(m),'-o',t/'probe']
 for name in ['anyhow','serde_json']:argv.extend(['--extern',name+'='+str(next(d.glob('lib'+name+'-*.rlib')))])
 sp.run(argv,check=True)
 def run(s,on=True,mode='json'):
  return json.loads(sp.check_output([t/'probe'],input=json.dumps({'text':s,'registered':on,'mode':mode},ensure_ascii=False),text=True))
 good=(p/'examples/expected-answer.md').read_text()
 def success(text,what):
  x=run(text);assert x['claimed'] and x['closed'];v=x['tree'];assert v['type']=='card' and v['title']=='100 листовок — учебный пример'
  tab=v['children'][0];assert tab==expected
  print(what+': accepted; 1 card, 4 column labels, all 12 cells matched by position.')
 expected={'type':'table','columns':['Типография','Цена за тираж','Срок','Бумага'],'rows':[['Буква','2 400 ₽','3 дня','матовая'],['Лист','2 750 ₽','1 день','глянцевая'],['Точка','2 200 ₽','5 дней','матовая']]}
 success(good,'First complete answer')
 x=good.replace('"2 200 ₽"', '2200'); err=run(x);assert err['error']=='table rows must contain one string per column';print('Mistake 1, numeric cell:',err['error']);success(x.replace('2200','"2 200 ₽"'),'Repaired price with quoted human-readable amount')
 x=good.replace('  "title": "100 листовок — учебный пример",\n','').replace('"type": "table",','"type": "table",\n    "title": "100 листовок — учебный пример",');err=run(x);assert err['error']=='unsupported field "title"';print('Mistake 2, title placed on the table:',err['error']);success(x.replace('    "title": "100 листовок — учебный пример",\n','').replace('"type": "card",','"type": "card",\n  "title": "100 листовок — учебный пример",'),'Restored title to enclosing card')
 off=run(good,False);assert off=={'claimed':False,'closed':True,'language':'json-render'}
 opened=run(good.split('\n```\n')[0]);assert opened=={'claimed':False,'closed':False,'language':'json-render'}
 print('Routing controls: closed but disabled/unregistered → not claimed; unfinished fence → not claimed.')
 simple=(p/'examples/simple-table.md').read_text();h=run(simple,False,'gfm')['html']
 class Table(html.parser.HTMLParser):
  def __init__(self):super().__init__();self.rows=[];self.c=None;self.t=0
  def handle_starttag(self,k,attrs):
   if k=='table':self.t+=1
   if k=='tr':self.rows.append([])
   if k in ('th','td'):self.c=[]
  def handle_data(self,s):
   if self.c is not None:self.c.append(s)
  def handle_endtag(self,k):
   if k in ('td','th'):
    self.rows[-1].append(''.join(self.c));self.c=None
 result=Table(); result.feed(h);assert result.t==1 and result.rows==[expected['columns'],*expected['rows']]
 print('Plain alternative: actual GFM conversion produced 1 HTML table; all 4 labels and 12 values identical, no json-render fence.')
 print(f'Offline replay wall seconds (includes compiling isolated Rust): {time.monotonic()-start:.3f}')
