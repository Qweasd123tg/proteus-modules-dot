#!/usr/bin/env python3
"""Exact Markdown tests, process output parity, and release allocation counters."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess as sp
import sys
import tempfile

BASE = "892f627570369ed60d7205eb0d351c753ec4305f"
HERE = Path(__file__).resolve().parent
PKG = "extension-markdown-render"
PACKAGE = Path("packages/markdown-render")
FENCE = chr(96) * 3


def ordinary(exe, src, env):
    features = json.loads((src / PACKAGE / "extension.json").read_text())["required_features"]

    def render(revision, source, languages, language="text/markdown"):
        return {"type":"render","context":"fixture","view":"article","surface":"content",
                "content":{"language":language,"source":source,"source_revision":revision,
                           "context":{"languages":languages}}}

    opened = f"До блока — **текст**.\n\n{FENCE}mermaid\nХод --> Итог"
    rust = "  let fixture = 'λ';\r\n"
    closed = f"{opened}\n{FENCE}\n\n~~~RuSt\r\n{rust}~~~\r\n"
    expanded = closed + "\n    indented sample\n\nПосле блока."
    inputs = [
        {"type":"hello","protocol":4,"features":features},
        render(1,opened,["mermaid"]), render(2,closed,["mermaid"]),
        render(3,expanded,["mermaid"]), render(4,expanded,[]),
        render(5,"literal <mark> & **bold**",[],"text/plain"),
        {"type":"close","view":"article"},
        render(6,closed,["mermaid"]),
        {"type":"close","view":"article"},
    ]
    data = b"".join(json.dumps(msg).encode() + b"\n" for msg in inputs)
    result = sp.run([exe],input=data,cwd=src / PACKAGE,env=env,capture_output=True,check=True,timeout=15)
    assert not result.stderr, result.stderr
    frames = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(f["type"], f["view"], f["source_revision"]) for f in frames] == [
        ("view","article",i) for i in range(1,7)]
    nodes = [{c["id"]:c for c in f["root"].get("children",[]) if "id" in c} for f in frames]
    def code(index, name, language, text):
        assert nodes[index][name] == {"type":"code","id":name,"language":language,"text":text,"embedded":True}

    code(0,"code-0","mermaid","Ход --> Итог")
    assert nodes[1]["code-0"]["type"] == "content" and nodes[1]["code-0"]["source"] == "Ход --> Итог\n"
    code(1,"code-1","rust",rust)
    assert nodes[1]["code-0"] == nodes[2]["code-0"]
    assert nodes[1]["code-1"] == nodes[2]["code-1"]
    code(2,"code-2","","indented sample")
    code(3,"code-0","mermaid","Ход --> Итог\n")
    code(3,"code-1","rust",rust)
    assert frames[4]["root"]["html"] == '<div style="white-space: pre-wrap">literal &lt;mark&gt; &amp; **bold**</div>'
    assert frames[1]["root"] == frames[5]["root"]
    return result.stdout


def main():
    with tempfile.TemporaryDirectory(prefix="markdown-move-embedded-code-") as path:
        root = Path(path)
        # Reuse one prepared target if supplied; each result is retained before the next build.
        target = Path(os.environ.get("R66_MARKDOWN_TARGET", root / "target")).resolve()
        arms = {}
        for arm, count in [("stock", 48), ("candidate", 49)]:
            src = root / arm
            env = dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_INCREMENTAL="0", TZ="UTC")
            sp.run(["git","-c","advice.detachedHead=false","clone","-q","--no-checkout",str(Path(sys.argv[1]).resolve()),src],check=True)

            def run(*cmd):
                result = sp.run(cmd,cwd=src,env=env,capture_output=True)
                if result.returncode:
                    raise RuntimeError((cmd, result.stderr.decode(), result.stdout.decode()))
                return result.stdout

            patch = HERE / "source.patch"
            run("git","checkout","-q","--detach",BASE)
            assert run("git","rev-parse","HEAD").decode().strip() == BASE
            run("git","apply","--index","--check",patch)
            if arm == "candidate":
                run("git","apply","--whitespace=error",patch)
                run("git","apply","--reverse","--check",patch)
                run("git","diff","--check")
            run("cargo","fmt","--check","-p",PKG)
            for profile, flags in [("debug", []), ("release", ["--release"])]:
                output = run("cargo","test","--locked","-j1","-p",PKG,*flags).decode()
                summary = next(line for line in output.splitlines() if line.startswith("test result:"))
                assert f"ok. {count} passed; 0 failed;" in summary, summary
                print(arm,profile,summary.split("; finished in",1)[0],flush=True)
            run("cargo","build","--release","--locked","-j1","-p",PKG)
            executable = target / "release" / "markdown-render"
            wire = ordinary(executable,src,env)

            main_rs = src / PACKAGE / "src/main.rs"
            marker = "fn main() {\n    run(Markdown::default());\n}"
            source = main_rs.read_text()
            assert source.count(marker) == 1
            main_rs.write_text(source.replace(marker,(HERE / "probe.rs").read_text()))
            renderer = src / PACKAGE / "src/render.rs"
            source = renderer.read_text()
            renderer.write_text(source + """
impl Document {
    pub(super) fn probe_code_size(&self) -> (usize, usize) {
        self.segments.iter().filter_map(|segment| {
            let Value::String(code) = &segment.node["text"] else { return None };
            Some((code.len(), code.capacity()))
        }).fold((0, 0), |(len, capacity), (n, c)| (len + n, capacity + c))
    }
}
""")
            run("cargo","build","--release","--locked","-j1","-p",PKG)
            results = run(executable,"outputs")
            counts = run(executable,"counts")
            assert all(run(executable,"counts") == counts for _ in range(4))
            arms[arm] = wire, results, counts

        stock, candidate = arms.values()
        assert stock[0] == candidate[0], "process bytes differ"
        assert stock[1] == candidate[1], "document bytes differ"
        for a,b in zip(stock[2].decode().splitlines(),candidate[2].decode().splitlines(),strict=True):
            a,b = a.split(),b.split()
            assert a[:2] == b[:2] and a[4:] == b[4:], (a,b)
            if a[0].startswith("embedded"):
                assert int(b[2]) < int(a[2]) and int(b[3]) < int(a[3]), (a,b)
            elif a[0] == "indented-eof":
                assert int(b[2]) <= int(a[2]) and int(b[3]) <= int(a[3]), (a,b)
            else:
                assert a == b, (a,b)
        for label,content in [("ordinary protocol frames",stock[0]),("instrumented document outputs",stock[1])]:
            print(label,len(content.splitlines()),len(content),sha256(content).hexdigest())
        print("case, source bytes, alloc/realloc calls, requested bytes, retained code len, retained code capacity: 5 identical observations per arm")
        for arm,(_,_,counts) in arms.items():
            for line in counts.decode().splitlines():
                print(arm,line)


if __name__ == "__main__":
    main()
