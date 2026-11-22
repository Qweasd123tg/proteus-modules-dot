"""Real packaged Node and Mermaid extension raw stdio fixtures. No API invocation."""
import hashlib
import json
from pathlib import Path
import subprocess as sp

THEME = {
    "foreground":"#e8e8ed","background":"#11131a","muted":"#8b8d98",
    "border":"#424454","accent":"#8aabff","danger":"#ff7e88",
    "surface":"#242633","surface_alt":"#303344",
    "font_family":"Inter, sans-serif","font_family_mono":"monospace",
}
SOURCE = "flowchart LR\n A[Привет 🦀] --> B[Мир]"


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",",":")).encode()


def frames():
    hello = {"type":"hello","protocol":4,"workspace":"/fixture",
             "features":["surfaces.content.v1","surfaces.preview.v1","widgets.svg.v1"]}
    common = {"context":"test","session_dir":"/fixture","view":"diagram"}
    source_limit = SOURCE + " "*(50_000-len(SOURCE.encode()))
    request_limit = 512*1024
    padded = dict(THEME, fixture_padding="")
    padded["fixture_padding"] = "x"*(request_limit-len(encode({"source":SOURCE,"theme":padded})))
    assert len(encode({"source":SOURCE,"theme":padded})) == request_limit
    endpoints = [
        ("first","content","mermaid",SOURCE,{"theme":THEME},"view"),
        ("repeat","content","mermaid",SOURCE,{"theme":THEME},"view"),
        ("change-theme","content","mermaid",SOURCE,{"theme":dict(THEME,foreground="#112233")},"view"),
        ("preview","preview","text/plain","ignored",{"theme":THEME},"view"),
        ("missing-theme","content","mermaid",SOURCE,{},"content_error"),
        ("null-theme","content","mermaid",SOURCE,{"theme":None},"content_error"),
        ("wrong-language","content","svg",SOURCE,{"theme":THEME},"content_error"),
        ("source-at","content","mermaid",source_limit,{"theme":THEME},"view"),
        ("source-over","content","mermaid",source_limit+"x",{"theme":THEME},"content_error"),
        ("request-at","content","mermaid",SOURCE,{"theme":padded},"view"),
        ("request-over","content","mermaid",SOURCE,{"theme":dict(padded,fixture_padding=padded["fixture_padding"]+"x")},"content_error"),
        ("invalid-diagram","content","mermaid","not-a-diagram Привет",{"theme":THEME},"content_error"),
        ("recover","content","mermaid","sequenceDiagram\n Аня->>Борис: Готово",{"theme":THEME},"view"),
    ]
    messages = [hello]
    for rev, (name,surface,language,source,ctx,kind) in enumerate(endpoints,1):
        messages.append({"type":"render","surface":surface,**common,"content":{
            "language":language,"source":source,"source_revision":rev,"context":ctx}})
        if name=="first":
            messages.append({"type":"render","surface":"content",**common,"view":"second","content":{
                "language":"mermaid","source":"sequenceDiagram\n X->>Y: Hello","source_revision":100,"context":{"theme":THEME}}})
    messages.extend([{"type":"close",**common,"view":"second"}, {"type":"close",**common}])
    expected = {i+1:(row[0],row[-1]) for i,row in enumerate(endpoints)}
    expected[100] = ("second","view")
    return b"".join(encode(m)+b"\n" for m in messages),expected


def worker_wire(binary,cwd,env):
    payload,expected = frames()
    result=sp.run([binary],input=payload,cwd=cwd,env=env,capture_output=True,check=True,timeout=15)
    assert not result.stderr, result.stderr
    replies={}
    for line in result.stdout.splitlines():
        row=json.loads(line)
        rev=row["source_revision"]
        assert rev not in replies and rev in expected, row
        name,kind=expected[rev]
        assert row["type"]==kind, (name,row)
        replies[rev]=row
    assert set(replies)==set(expected)
    assert replies[1]["root"]==replies[2]["root"]==replies[8]["root"]==replies[10]["root"]
    assert replies[3]["root"]!=replies[1]["root"] and "#112233" in replies[3]["root"]["source"]
    assert "Запрос" in replies[4]["root"]["source"] and "ignored" not in replies[4]["root"]["source"]
    assert replies[5]["error"]==replies[6]["error"]
    assert replies[7]["error"]=="unsupported Mermaid language"
    assert replies[9]["error"]=="Mermaid source exceeds 50,000 bytes"
    assert replies[11]["error"]=="Mermaid request is too large"
    assert "Готово" in replies[13]["root"]["source"]
    return result.stdout


PACKAGE = Path("packages/mermaid-render")
WORKER_FILES = {
    "worker.mjs":"9b9aab8e03aa4cbf17034a7693845a18396e08ff1d39d1323c206a9a211e0948",
    "svg-theme.mjs":"cb1e3bb5b081b5db9a4c94135b649218dbd57f18a96c077236719fad2aa256c6",
    "vendor/pele/pele.mjs":"a87cc1dc5b2334ccfe32fd0aa5c66f2bb1006b035642976031f589d70c6bf9c7",
    "tests/worker.test.mjs":"45dc31c157235b05d744879a7fd0d3b6ffec4fa9a73b4ff8cc5bcde9cac5154d",
    "tests/wire.rs":"37427f3d17508115a3a7f072cbef123ef4683d0ad03f3e201ca9f13d0f2f8704",
}


def check_worker(cwd):
    got={name:hashlib.sha256((cwd/name).read_bytes()).hexdigest() for name in WORKER_FILES}
    assert got==WORKER_FILES,got


def layered(steps):
    # Four stable lanes through sequential stages and occasional handoffs.
    ids = ["Queued","Validation","Prepared","Committed"]
    rows = ["flowchart LR"]
    for j in range(steps):
        for i,name in enumerate(ids):
            rows.append(f'  G{j}{i}["{name} {j:02}: этап {i}"] --> G{j+1}{i}')
            if i < 3 and j % 3 == 0:
                rows.append(f"  G{j}{i} -.-> G{j+1}{i+1}")
    for i,name in enumerate(ids):
        rows.append(f'  G{steps}{i}["{name}: готово"]')
    return "\n".join(rows)


def sequence(steps):
    kinds = (
        ("Client","Gateway","Request","->>"),
        ("Gateway","Validate","Policy check","->>"),
        ("Validate","Gateway","Accepted","-->>"),
        ("Gateway","Store","Save record","->>"),
        ("Store","Gateway","Saved","-->>"),
        ("Gateway","Client","Result готов","-->>"),
    )
    rows = ["sequenceDiagram"]+[f"  participant {name}" for name in ("Client","Gateway","Validate","Store")]
    for n in range(steps):
        left,right,message,arrow = kinds[n%len(kinds)]
        rows.append(f"  {left}{arrow}{right}: {message} {n:03}")
    return "\n".join(rows)


def diagrams():
    return {"small":SOURCE,"flow-97":layered(19),"sequence-96":sequence(96)}


def actual_worker(cwd, env, node):
    check_worker(cwd)
    data=diagrams()
    requests=[encode({"source":code,"theme":THEME}) for code in data.values()]
    assert all(len(req)<=512*1024 and len(code.encode())<=50_000
               for req,code in zip(requests,data.values(),strict=True))
    actual=sp.run([node,"--max-old-space-size=96","--no-addons","worker.mjs"],
                  input=b"\n".join(requests)+b"\n",cwd=cwd,env=env,
                  capture_output=True,check=True,timeout=20)
    assert not actual.stderr, actual.stderr
    replies=dict(zip(data,actual.stdout.splitlines(keepends=True),strict=True))
    for name,raw in replies.items():
        reply=json.loads(raw)
        assert reply["ok"] is True,(name,reply)
        svg=reply["svg"].encode()
        assert svg.startswith(b"<svg") and len(svg)<=1024*1024
        assert all(1<=reply[d]<=4096 for d in ("width","height"))
    return replies


def large_wire(binary, cwd, env, replies):
    data=diagrams()
    hello={"type":"hello","protocol":4,"workspace":"/fixture",
           "features":["surfaces.content.v1","surfaces.preview.v1","widgets.svg.v1"]}
    reqs=[hello]
    plans=(
        ("one","/fixture-a","fig-a","flow-97",50),
        ("one","/fixture-a","fig-a","flow-97",51),
        ("two","/fixture-b","fig-b","flow-97",52),
        ("two","/fixture-b","fig-c","sequence-96",53),
    )
    for context,session,view,name,rev in plans:
        reqs.append({"type":"render","context":context,"session_dir":session,"view":view,
                     "surface":"content","content":{"language":"mermaid","source":data[name],
                     "source_revision":rev,"context":{"theme":THEME}}})
    for context,session,view,_,_ in (plans[0],plans[2],plans[3]):
        reqs.append({"type":"close","context":context,"session_dir":session,"view":view})
    inp=b"".join(encode(r)+b"\n" for r in reqs)
    actual=sp.run([binary],input=inp,cwd=cwd,env=env,capture_output=True,check=True,timeout=20)
    assert not actual.stderr, actual.stderr
    wire=[json.loads(r) for r in actual.stdout.splitlines()]
    assert [v["source_revision"] for v in wire]==[row[-1] for row in plans],wire
    for row,(_,session,view,name,rev) in zip(wire,plans,strict=True):
        expected=json.loads(replies[name])
        assert row["type"]=="view" and row["view"]==view and row["session_dir"]==session and row["sequence"]==0,row
        assert row["root"]=={"type":"svg","source":expected["svg"],"width":expected["width"],"height":expected["height"]},name
    return actual.stdout
