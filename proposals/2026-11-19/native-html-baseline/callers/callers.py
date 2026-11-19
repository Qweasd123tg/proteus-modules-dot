"""Verify pinned source identities, direct app ownership and controlled wire witnesses.
Not a GUI instrument: bounds concern one retained live state and a drained queue.
Usage: python3 callers.py DESKTOP EXTENSIONS NATIVE_MARKDOWN_RENDER
"""
import hashlib,json,math,re,subprocess,sys
from pathlib import Path
D,E,B=map(Path,sys.argv[1:]); pins=json.loads(Path(__file__).with_name('pins.json').read_text())
for key,expected in pins.items():
 prefix,relative=key.split('/',1); data=({'desktop':D,'extensions':E}[prefix]/relative).read_bytes()
 assert hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()==expected,key
assert json.loads((D/'repositories.json').read_text())['extensions']['rev']=='a35cea08be83ee8e5ecbfce9ef5050a1c00eb247'
def code(path):return (D/path).read_text()
p='vendor/gpui-base/src/text/'; q='src/ui/extensions/declarative/'
s=code(p+'state.rs')
limit=int(re.search(r'const MAX_COALESCED_UPDATES_PER_PARSE: usize = (\d+);',s)[1])
assert limit==64
assert 'const MAX_SYNC_FULL_REPLACE_BYTES: usize = 4 * 1024;' in s
app_paths={}
for directory in ('src','crates','examples'):
 for f in (D/directory).rglob('*.rs'):
  for i,line in enumerate(f.read_text().splitlines(),1):
   if re.search(r'\bTextViewState\b|\bTextView::(?:html|markdown|new)\(',line):app_paths.setdefault(str(f.relative_to(D)),[]).append(i)
assert set(app_paths)=={q+'rich_text.rs',q+'inline_content.rs'}
for needle in ('TextViewState::html(html, cx)','if self.html != html','state.set_text(html, cx)','TextView::new(&self.state)'):
 assert needle in code(q+'rich_text.rs')
assert 'push_str(' not in code(q+'rich_text.rs')+code(q+'inline_content.rs')
assert 'self.format == TextViewFormat::Markdown' in s and 'self.push_str(delta, cx)' in s
assert 'text: None' in code(p+'text_view.rs').split('pub fn new(state:')[1].split('pub fn markdown(')[0]
assert 'pub fn push_str(&mut self, new_text:' in s and 'fn html_push_str_keeps_earlier_blocks' in s

# Enumerate possible terminal batch sizes (polls may drain from 1 to 64) via DP.
lo=[0];hi=[0]
for n in range(1,131):
 lo.append(1+min(lo[max(0,n-limit):n]));hi.append(1+max(hi[max(0,n-limit):n]))
 assert (lo[n],hi[n])==(math.ceil(n/limit),n)
stats={str(n):{'ui_sync':n,'stock_background_parse_range':[lo[n],hi[n]],'deferred_background_parses':0} for n in [1,4,16,64,65,128,130]}

# Replay the released renderer: first plain short body, exact repeat, changed prefix,
# inline math creates a slot, then plain prose removes it; same retained rich_text id.
samples=['Ответ','Ответ','Ответ растёт','Ответ: $x$ и **итог**.','Снова проза']
def encode(m):return json.dumps(m,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
hello={'type':'hello','protocol':4,'features':['surfaces.content.v1','widgets.rich_text.v1','widgets.rich_text.inlines.v1','widgets.content.v1','widgets.code_embedded.v1'],'workspace':'/synthetic','server':{'origin':'','token':''}}
body=encode(hello)
for i,md in enumerate(samples,1):
 body+=encode({'type':'render','view':'callers:one','surface':'content','argument':'assistant','context':'fixture','session_dir':'/synthetic','content':{'source':md,'source_revision':i,'language':'text/markdown','context':{'languages':['latex']}}})
r=subprocess.run([str(B.resolve())],input=body,capture_output=True,check=True,timeout=15)
assert r.stderr==b''
def nodes(root):
 if isinstance(root,list):
  for v in root:yield from nodes(v)
 elif isinstance(root,dict):
  if root.get('type')=='rich_text':yield root
  for v in root.values():yield from nodes(v)
frames=[]
for rev,line in enumerate(r.stdout.splitlines(),1):
 m=json.loads(line);assert m['type']=='view' and m['source_revision']==rev
 n,=nodes(m['root'])
 frames.append({'revision':rev,'id':n['id'],'html':n['html'],'html_utf8_bytes':len(n['html'].encode()),'inline_count':len(n.get('inlines',[]))})
assert len(frames)==5 and len({f['id'] for f in frames})==1
assert [f['inline_count'] for f in frames]==[0,0,0,1,0]
assert frames[0]['html']==frames[1]['html'] and all(f['html_utf8_bytes']<=4096 for f in frames)
print(json.dumps({'pinned_source_files_verified':len(pins),'desktop_direct_type_reference_lines':app_paths,
  'idealized_replacement_bounds':stats,'process_sha256':hashlib.sha256(B.read_bytes()).hexdigest(),
  'raw_stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'native_wire':frames},ensure_ascii=False,indent=2))
