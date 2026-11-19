"""Render controlled Markdown/text inputs using the unmodified real extension protocol."""
import argparse, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("binary", type=Path);p.add_argument("out",type=Path);o=p.parse_args()
samples=[]
def extract(v):
    if isinstance(v, dict):
        if v.get("type")=="rich_text": yield v["html"]
        for c in v.values():yield from extract(c)
    elif isinstance(v,list):
        for c in v:yield from extract(c)
hello={"type":"hello","protocol":4,"workspace":"/synthetic","features":["surfaces.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1","widgets.content.v1","widgets.code_embedded.v1"]}
def render(name,lang,source,save=True):
    # Fresh extension for each source: no incremental/context or fixture cross-talk.
    request={"type":"render","context":"s","surface":"content","view":"v","session_dir":"/synthetic","content":{"language":lang,"source":source,"source_revision":1,"context":{"languages":["latex"]}}}
    cp=subprocess.run([o.binary.resolve()],input=json.dumps(hello)+'\n'+json.dumps(request)+'\n',capture_output=True,text=True,check=True)
    messages=[json.loads(l) for l in cp.stdout.splitlines()]
    assert len(messages)==1 and messages[0]['type']=='view'
    vals=list(extract(messages[0]))
    assert len(vals)==1,(name,[(v.get('type')) for v in messages],len(vals),str(messages[0])[:512])
    if save:samples.append({'name':name,'language':lang,'source':source,'html':vals[0]})
    return vals[0]
def pad_to_html(name,lang,body,target):
    html=render(name,lang,body,False); n=target-len(html.encode())
    assert n>=0,(name,n)
    html=render(name,lang,body+'x'*n)
    assert len(html.encode())==target, (name,len(html.encode()))
plain='text/plain'; md='text/markdown'
for n,lang,source in [
    ('plain-ack',plain,'Готово.'),
    ('plain-escape',plain,'if (left < right && value > 0) {\n  say("да");\n}'),
    ('plain-link',plain,'Подробности: https://example.org/docs?a=1&b=2'),
    ('md-selection',md,'## Итог\n\nВыделить **слово** и [ссылку](https://example.org).\n\nВторая строка: `a < b`, *дальше*.'),
    ('md-table',md,'| Field | Значение |\n| --- | --- |\n| **Name** | A & B |\n| Link | [doc](https://example.org/doc) |'),
]: render(n,lang,source)
for sz in [4095,4096,4097]:
    pad_to_html(f'plain-{sz}',plain,'Отчёт. ',sz)
table='| Key | Value |\n| --- | --- |\n'+''.join(f'| a{i} | [{i}](https://example.org/{i}) |\n' for i in range(24))+'\nИтог: '
pad_to_html('md-table-4096',md,table+'x',4096)
link=('Текст [документ](https://example.org) **важно**. '*15)+'\n\nИтог: '
pad_to_html('md-links-4096',md,link+'x',4096)
o.out.write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in samples))
print(len(samples),'real renderer outputs;',[(s['name'],len(s['html'].encode())) for s in samples])
