"""Combine the tiny control cases and the #217 synthetic long real-HTML control."""
import hashlib,json,subprocess,sys
from pathlib import Path
fixtures,renderer,prose=map(Path,sys.argv[1:])
text=prose.read_text()
assert hashlib.sha256(text.encode()).hexdigest()=='a26645d9e976f9729c7b2b59306f0a12244b3c2ffc0b393e773f7d0005158a90'
hello={'type':'hello','protocol':4,'workspace':'/synthetic','features':['surfaces.content.v1','widgets.rich_text.v1','widgets.rich_text.inlines.v1','widgets.content.v1']}
req={'type':'render','context':'s','surface':'content','view':'v','session_dir':'/fixture','content':{'language':'text/markdown','source':text,'source_revision':1,'context':{'languages':['json-render','svg','md','markdown','mermaid']}}}
res=subprocess.run([renderer.resolve()],text=True,input=json.dumps(hello)+'\n'+json.dumps(req)+'\n',capture_output=True,check=True)
root=json.loads(res.stdout)['root']['children'];assert len(root)==1 and root[0]['type']=='rich_text'
html=root[0]['html'];assert hashlib.sha256(html.encode()).hexdigest()=='5298d1d9b630939bb28f24ade40651300885b5ef2b0982120be5610b1e87ea50'
sys.stdout.write(fixtures.read_text())
print(json.dumps({'name':'long-markdown-html','html':html},ensure_ascii=False))
