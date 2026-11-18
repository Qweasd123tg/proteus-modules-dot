"""Produce synthetic Widget::RichText HTML from the actual pinned renderer's protocol."""
import json, sys, subprocess, hashlib
from itertools import product
from pathlib import Path
bin, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]); cases=[]
def extract(v):
    if isinstance(v,dict):
        if v.get("type")=="rich_text": yield v["html"]
        for c in v.values():yield from extract(c)
    if isinstance(v,list):
        for c in v:yield from extract(c)
hello={"type":"hello","protocol":4,"workspace":"/synthetic","features":["surfaces.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1","widgets.content.v1","widgets.code_embedded.v1"]}
p=subprocess.Popen([bin],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def send(v):p.stdin.write(json.dumps(v,ensure_ascii=False)+"\n");p.stdin.flush()
send(hello)
def render(category,lang,source):
    i=len(cases)+1
    send({"type":"render","context":"s","surface":"content","view":"v","session_dir":"/synthetic","content":{"language":lang,"source":source,"source_revision":i,"context":{"languages":["latex"]}}})
    msg=json.loads(p.stdout.readline())
    assert msg["type"]=="view"
    for html in extract(msg):cases.append((category,html))
text='Обычный вопрос про файл: x < y && y > z. \n**это буквальный текст**\n'
render("plain53","text/plain",text*512+" 0")
render("plain53url","text/plain",text*512+" https://example.org/x 0")
ordinary=("A paragraph about parsing documents and preserving their layout. "
          "Вопрос о выводе текста и поддержке разных языков.\n")
render("sentence53","text/plain", (ordinary*700).encode()[:53010].decode("utf8","ignore"))
render("sentence53url","text/plain", (ordinary*700).encode()[:53010].decode("utf8","ignore")+" https://example.org/x")
for a,b in product(["", "Two spaces  here. ", "Кириллица & < >", "\n\n\t ", 'Quoted "x"','*value*\n','漢字 🦀'],["end","https://example.org/q?a=1&b=2","www.example.org","x\n","\r\n"]):
    render("plain","text/plain",a+b)
for a,b in product(["", "# Heading\n\n","- one\n- two\n\n","> quote\n\n", "## Chapter\n\n","| A | B |\n|---|---|\n| 1 | 2 |\n\n"],["Text","**bold** and _italic_","\n\n[example](https://example.org)","a  b\nnext",'`42` and $a+b$',"Café 🦀 &amp;"]):render("markdown","text/markdown",a+b)
p.stdin.close();assert p.wait()==0
for a,b in product(["<div>{}</div>","<p>{}</p>","<b>{}</b>","<pre>{}</pre>","<p class='x'>{}</p>","<!--c--><div>{}</div>","<textarea>\n{}</textarea>","<table><tr><td>{}"," <strong>{} </strong>","<a href=https://e.test/>{}</a>","<div data-content=slot>{}</div>"],["","x","🦀  \n text","&#65;","&lt;","x\r\ny","&amp;quot;","\x00","a<!-- xx -->b","\n\n"]):cases.append(("independent-html",a.format(b)))
cases += [("large-miss","<p>"+"a   b   &amp;    c "*20000+"</p>"),("large-hit",'<div style="white-space: pre-wrap">'+"word "*80000+"</div>")]
out.write_text("".join(json.dumps(c,ensure_ascii=False)+"\n" for c in cases))
print("total",len(cases),"bytes",out.stat().st_size,"source binary SHA256",hashlib.sha256(bin.read_bytes()).hexdigest())
