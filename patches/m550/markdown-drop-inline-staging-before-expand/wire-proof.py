"""Native Markdown HTML and raw inline-source parity; no downstream TeX/Node process."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

binary,out=(Path(p).resolve() for p in sys.argv[1:3])
meter=Path(sys.argv[3]) if len(sys.argv)==4 else None
first="/synthetic/primary"
second="/synthetic/reopened"
unicode_run="α+xy123 " 
large_bodies=[f"{i}x"+(unicode_run*2000)+"z" for i in range(64)]
large_new=large_bodies.copy(); large_new[31]=large_new[31][:-1]+"q"
def doc(bodies):
    return "\n\n".join(f"Expression {i}: ${body}$ end." for i,body in enumerate(bodies))
limit="λ"*(32768//2)
over="y"*32769
bounds=f"Exact ${limit}$ end.\r\n\r\nToo large ${over}$ end."
count=":PROTEUSINLINE0X0: " + "$x$ "*258
footnotes=("[^n]: Footnote $y$\n\n"+
           "\n\n".join(f"[^hidden{i}]: Invisible ${'m'*8100}z$" for i in range(4))+
           "\n\nBody $x$; two references[^n], again[^n].")
mixed=r"""Price $100 then **$x<y & z$**, raw $xy+\$unit$, and `$literal$`.

<script>not rendered</script>

![alt $no$](https://example.invalid/a.png)
"""
frames=[{"type":"hello","protocol":4,"features":[
    "surfaces.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1",
    "widgets.content.v1","widgets.code_embedded.v1"]}]
def message(n,source,langs,session=first):
    return {"type":"render","view":"math","context":session,"session_dir":session,
            "surface":"content","content":{"language":"text/markdown","source":source,
                                           "source_revision":n,"context":{"languages":langs}}}
frames += [
    message(1,doc(large_bodies),["tex","latex"]),message(2,doc(large_bodies),["tex","latex"]),
    message(3,doc(large_new),["tex","latex"]),message(4,bounds,["latex"]),
    message(5,count,["latex"]),message(6,footnotes,["latex"]),
    message(7,mixed,["latex"]),message(8,mixed,[]),
    {"type":"close","view":"math","context":first,"session_dir":first},
    message(9,mixed,["tex"],second),
]
run=subprocess.run([binary],input=b"".join((json.dumps(v,ensure_ascii=False)+"\n").encode() for v in frames),
                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=120)
if meter:
    logs=run.stderr.decode().splitlines()
    assert len(logs)==8 and all(line.startswith("alloc ") for line in logs),logs[:10]
    meter.write_text(run.stderr.decode())
else:
    assert not run.stderr,run.stderr[:700]
rows=list(map(json.loads,run.stdout.splitlines()))
assert len(rows)==9
for i,r in enumerate(rows,1):
    assert r["type"]=="view" and r["source_revision"]==i and r["view"]=="math"
    assert r["session_dir"]==(first if i<9 else second)
    assert len(r["root"]["children"])==1
def prose(n):
    return rows[n-1]["root"]["children"][0]
def sources(n):
    return [item["source"] for item in prose(n).get("inlines",[])]
assert sources(1)==large_bodies and sources(3)==large_new and prose(1)==prose(2)
assert all(item["language"]=="latex" for item in prose(1)["inlines"])
assert sources(4)==[limit] and over in prose(4)["html"]
assert sources(5)==["x"]*256 and prose(5)["html"].count("data-content=")==256
assert prose(5)["html"].endswith("$x$ $x$</p>") and ":PROTEUSINLINE0X0:" in prose(5)["html"]
assert sources(6)==["y","x"],[(len(x),x[:80]) for x in sources(6)]
assert "Invisible" not in prose(6)["html"] and "PROTEUSINLINE" not in prose(6)["html"]
assert sources(7)==["x<y & z",r"xy+\$unit"],sources(7)
assert "$100" in prose(7)["html"] and "%100" not in prose(7)["html"]
assert "$x&lt;y &amp; z$" in prose(7)["html"]
assert "<script>" not in prose(7)["html"] and '<code>$literal$</code>' in prose(7)["html"]
assert sources(8)==[] and 'data-content=' not in prose(8)["html"]
assert sources(9)==sources(7) and all(item["language"]=="tex" for item in prose(9)["inlines"])
out.write_bytes(run.stdout)
print(len(rows),len(run.stdout),sha256(run.stdout).hexdigest())
