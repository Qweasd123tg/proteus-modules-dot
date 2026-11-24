"""Exercise real Markdown binary over NDJSON; reference scope must survive streaming."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

binary, output = (Path(p).resolve() for p in sys.argv[1:])
synth = "/synthetic/references"
hello = dict(type="hello",protocol=4,features=["surfaces.content.v1","widgets.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1","widgets.code_embedded.v1"])
head = "Привет [вперёд][later] [раз][a] [контейнер][nested]\r\n\r\n"
prefix = ('> [nested]: https://example.invalid/nested "строка в цитате"\r\n\r\n'
          '[a]: https://example.invalid/first "Я \\"quote\\""\r\n' +
          ''.join(f'[fixture-{n}]: https://example.invalid/{n} "' + "Я🦀" * 48 + '"\r\n'
                  for n in range(500)) +
          "\r\n```mermaid\r\nflowchart LR\r\n А-->Б\r\n```\r\n")
stem = head + prefix
tail = ("\r\nпосле: [x][later] [первый][a]\r\n\r\n"
        '[a]: https://example.invalid/duplicate\r\n'
        '[later]: https://example.invalid/later "🦀 title"\r\n')
fixtures = [
    (stem+"\r\nпосле: [x][later] [первый][a]\r\n", ["mermaid"]),
    (stem+tail, ["mermaid"]),
    (stem+tail+"\r\nдописали", ["mermaid"]),
    (stem+tail.replace("/later", "/edited"), ["mermaid"]),
    (stem+tail.replace("/later", "/edited"), []),
    (stem.replace("/first", "/changed")+tail, ["mermaid"]),
    (stem + "\r\nотменили позднюю ссылку", ["mermaid"]),
]
def render(rev, body, languages, address="left"):
    return dict(type="render",context=address,session_dir=synth+address,view="alias",
                surface="content",content=dict(language="text/markdown",source=body,source_revision=rev,
                                               context=dict(languages=languages)))
frames = [hello, *(render(n,text,lang) for n,(text,lang) in enumerate(fixtures,1)),
          dict(type="close",context="left",session_dir=synth+"left",view="alias"),
          render(8,"Открыли заново [несуществующая][a]", ["mermaid"], "right")]
encoded = b"".join((json.dumps(x,ensure_ascii=False)+"\n").encode() for x in frames)
run = subprocess.run([binary], input=encoded, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     check=True, timeout=45)
assert not run.stderr, run.stderr[:500]
out=[json.loads(s) for s in run.stdout.splitlines()]
assert [(row["type"],row["source_revision"]) for row in out] == [("view",n) for n in range(1,9)]
html=lambda idx:"".join(n.get("html","") for n in out[idx-1]["root"]["children"])
for n in range(1,8):
    assert 'example.invalid/nested' in html(n)
    assert 'example.invalid/duplicate' not in html(n)
    nodes = [s for s in out[n-1]["root"]["children"] if s["id"]=="code-0"]
    assert len(nodes)==1 and nodes[0]["type"]==("code" if n==5 else "content")
    assert nodes[0]["text" if n==5 else "source"] == "flowchart LR\r\n А-->Б\r\n"
for n in (2,3,6):
    assert 'example.invalid/later' in html(n)
for n in (1,7):
    assert 'example.invalid/later' not in html(n)
for n in (4,5):
    assert 'example.invalid/edited' in html(n)
assert 'example.invalid/changed' in html(6)
assert 'example.invalid/first' in html(7)
assert 'href=' not in html(8) and 'несуществующая' in html(8)
output.write_bytes(run.stdout)
print(f"{len(out)} frames {len(run.stdout)} bytes SHA256 {sha256(run.stdout).hexdigest()}")
