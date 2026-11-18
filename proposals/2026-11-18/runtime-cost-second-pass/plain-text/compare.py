"""Linux: compare two unmodified release extension executables over their JSONL protocol."""
import hashlib
import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

HELLO = {"type":"hello","protocol":4,"workspace":"/fixture","features":["surfaces.content.v1","widgets.rich_text.v1","widgets.rich_text.inlines.v1","widgets.content.v1","widgets.code_embedded.v1"]}
def line(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",",":")).encode() + b"\n"

def render_input(src, i):
    return line({"type":"render","context":"scope","surface":"content","view":"user","session_dir":"/fixture-session","content":{"language":"text/plain","source":src,"source_revision":i,"context":{"languages":["latex"]}}})

def batch(binary, sources, checks=False):
    requests = [render_input(s, i+1) for i,s in enumerate(sources)]
    with subprocess.Popen([str(binary)], stdin=subprocess.PIPE,stdout=subprocess.PIPE) as p:
        p.stdin.write(line(HELLO) + render_input("warmup",0)); p.stdin.flush()
        warm = p.stdout.readline()
        assert json.loads(warm)["root"]["type"] == "rich_text"
        times, outputs = [], []
        for req in requests:
            start = time.perf_counter_ns()
            p.stdin.write(req); p.stdin.flush(); raw = p.stdout.readline()
            times.append(time.perf_counter_ns()-start)
            assert raw, "extension returned no output"
            outputs.append(raw)
        proc = Path(f"/proc/{p.pid}/status").read_text().splitlines()
        rss_kib = int(next(r for r in proc if r.startswith("VmHWM:")).split()[1])
        p.stdin.close()
        assert p.wait(timeout=5) == 0
    if checks:
        for i,raw in enumerate(outputs,1):
            msg=json.loads(raw); assert msg["source_revision"] == i and msg["root"]["type"]=="rich_text"
    return sum(times)/len(times)/1e6, rss_kib, hashlib.sha256(b"".join(outputs)).hexdigest()

def inputs():
    src="Покажи изменения в отчёте и объясни, почему цифры отличаются."
    prose='Обычный вопрос про файл: x < y && y > z. \n**это буквальный текст**\n'
    return {
        "short plain": (src, 256),
        "short URL": (src+" https://example.org/q?a=1&b=2", 256),
        "long plain": (prose*512, 8),
        "long URL at end": (prose*512+" https://example.org/x", 6),
        "large multiline paste": (prose*8192, 2),
    }
def corpus():
    tokens = ["", "\r", "\n", "\r\n", "\x00", "\ufeff", " &<>\"' ", "[]()", "🙂","漢字",
              "пример.рф", "www.example.com", "abc@site.tld", "http:", "http:/", "https:/", "://", "x://y",
              "Https://example.org", "HTTP://example.org", "https://example.org/x?q=1&u=2",
              "http://example.org", "https://例子.中国/y", "(https://example.org/p(a)).", "<https://example.org>"]
    rng=random.Random(214)
    return tokens+[a+b for a in tokens for b in tokens]+["".join(rng.choices(tokens,k=rng.randrange(1,20))) for _ in range(512)]

def main(before, after):
    sides={"before": Path(before).resolve(),"after": Path(after).resolve()}
    hashes_by_side = {s: hashlib.sha256(p.read_bytes()).hexdigest() for s,p in sides.items()}
    assert hashes_by_side["before"] != hashes_by_side["after"], "same executable: check build directories"
    values=corpus()
    hashes=[batch(b,values,True)[2] for b in sides.values()]
    assert hashes[0]==hashes[1]
    result={"binary_sha256":hashes_by_side,"corpus":{"count":len(values),"sha256_complete_output":hashes[0]},"series":{}}
    for name,(body,n) in inputs().items():
        # Alternate a harmless ASCII suffix so successive calls also change the text.
        sources=[body+' '+str(i%2) for i in range(n)]
        runs={s:[] for s in sides}; ref=None
        for i in range(9):  # initial pair not counted
            for s in (("before","after") if i%2==0 else ("after","before")):
                ms,kib,digest=batch(sides[s],sources,True)
                if ref is None: ref=digest
                assert digest==ref
                if i: runs[s].append({"ms_per_round_trip":round(ms,5),"rss_kib":kib})
        result["series"][name]={"bytes_per_message":len(sources[0].encode()),"messages_per_process":n,
            "digest":ref,"samples":runs,"median":{s:{k:statistics.median(r[k] for r in obs) for k in obs[0]} for s,obs in runs.items()}}
        print(name,result["series"][name]["median"],file=sys.stderr,flush=True)
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    main(*sys.argv[1:])
