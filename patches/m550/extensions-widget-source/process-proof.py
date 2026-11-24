import json, subprocess, sys, hashlib
from pathlib import Path
out=Path(sys.argv[1]); b=Path(sys.argv[2]); out.mkdir(exist_ok=True)
def run(name, lang, sources, expected):
    frames=[dict(type="hello",protocol=4,workspace="/fixture",features=["surfaces.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1","widgets.content.v1","widgets.code_embedded.v1","widgets.svg.v1"])]
    for rev,source in enumerate(sources,1):
        frames.append(dict(type="render",context="scope-a",surface="content",view="id",session_dir="/synthetic-a",content=dict(source=source,language=lang,source_revision=rev,context=dict(languages=["mermaid"]))))
    encoded=b''.join((json.dumps(v,ensure_ascii=False)+'\n').encode() for v in frames)
    p=subprocess.run([str(b/name)],input=encoded,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=True)
    replies=[json.loads(line) for line in p.stdout.splitlines()]
    assert len(replies)==len(expected),str(replies)[:180]
    for rev,(reply,want) in enumerate(zip(replies,expected),1):
        assert reply['source_revision']==rev
        node=reply['root'] if name=='json-render' else next(n for n in reply['root']['children'] if n['type']=='content')
        assert node['source']==want
    (out/(name+'.ndjson')).write_bytes(p.stdout)
    print(name,len(p.stdout),hashlib.sha256(p.stdout).hexdigest())
body="A --> B: Я🦀 &amp; \"\n"*5200
short="B --> C\n"
run("markdown-render","text/markdown",["# One\n\n```mermaid\n"+s+"```\n" for s in [body,short,body]],[body,short,body])
svg='<svg xmlns="http://www.w3.org/2000/svg" width="70" height="5"><desc>'+('Я🦀 &amp; '*14500)+'</desc></svg>'
svg2='<svg viewBox="0 0 50 9"></svg>'
run("json-render","svg",[svg,svg2,svg],[svg,svg2,svg])
