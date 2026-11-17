"""Independent semantic check of 3 printed fields per label, not a Markdown reimplementation."""
import itertools, json, pathlib, subprocess, tempfile, sys, os
if len(sys.argv) != 3:
    raise SystemExit("usage: python3 check.py BASE_CORE_TREE PATCHED_CORE_TREE")
roots = dict(zip(("base", "candidate"), map(lambda name: pathlib.Path(name).resolve(), sys.argv[1:])))
fixture = pathlib.Path(__file__).resolve().with_name("renderer.rs")
rust = "rustc"
cases = ["/home/me/my work", "обычный/путь", "/tmp/a`b", "paper``notes", "`wrap`", "  spaced  ", "  ", "`", "x\\`y", " alpha``beta ", "vol/🦊`notes", "end```", "  start", "end  "]
cases += ["".join(parts) for length in range(1, 5) for parts in itertools.product(["a"," ","`"], repeat=length)]
cases = list(dict.fromkeys(cases))
labels=["cwd","config_path","model"]
rel=pathlib.Path("crates/proteus-core/src/core/topology_render/markdown.rs")
def gh_markdown(paragraphs):
    source="\n\n".join(paragraphs)+"\n"
    ast=json.loads(subprocess.check_output(["pandoc","-f","gfm","-t","json"],input=source.encode()))
    blocks=ast["blocks"]
    assert len(blocks)==len(paragraphs), (len(blocks),len(paragraphs))
    return [b["c"] for b in blocks]
def read_fields(document):
    return {lbl:next(line for line in document.splitlines() if line.startswith(lbl+": ")) for lbl in labels}
with tempfile.TemporaryDirectory() as tmp:
    d=pathlib.Path(tmp)
    results={}
    controls={}
    for variant in ["base","candidate"]:
        mod=roots[variant]/rel
        cmd=[rust,"--edition","2024","-D","warnings",str(fixture)]
        env={**os.environ,"PINNED_MARKDOWN_RS":str(mod)}
        subprocess.run(cmd+["-o",str(d/variant)],check=True,env=env)
        subprocess.run(cmd+["--test","-o",str(d/(variant+"-test"))],check=True,env=env)
        test_run=subprocess.run([str(d/(variant+"-test"))],text=True,capture_output=True)
        test=test_run.stdout
        print(variant+" Rust test binary: "+next(line for line in test.splitlines() if line.startswith("test result:")))
        if variant=="base":
            assert test_run.returncode!=0 and "topology_report_keeps_path_with_a_literal_backtick_in_one_code_span ... FAILED" in test
            print("  expected failure in same Rust test on unmodified full rendering function")
        else:
            assert test_run.returncode==0, test
        docs=subprocess.check_output([str(d/variant),*cases]).decode().split("\0")[:-1]
        controls[variant]=docs[:2]
        assert len(cases)==len(docs)
        paragraphs=[]
        expected=[]
        for value,doc in zip(cases,docs):
            fields=read_fields(doc)
            for label in labels:
                paragraphs.append(fields[label])
                expected.append((label,"example/"+value if label=="model" else value))
        mismatches=[]
        for line, nodes,(label,exp) in zip(paragraphs,gh_markdown(paragraphs),expected):
            actual=["bad AST",nodes]
            if len(nodes)==3 and nodes[0]=={"t":"Str","c":label+":"} and nodes[1]=={"t":"Space"} and nodes[2]["t"]=="Code":
                actual=nodes[2]["c"][1]
            if actual!=exp:
                mismatches.append((line,exp,actual))
        results[variant]=len(mismatches)
        print(f"{variant}: {len(cases)} nonempty labels, {len(expected)} field checks, {len(mismatches)} mismatches")
        for mismatch in mismatches[:2]:
            print("  example:", json.dumps(mismatch, ensure_ascii=False))
        if variant=="base":
            assert any(x[1]=="/tmp/a`b" for x in mismatches)
            assert any(x[1]=="  spaced  " for x in mismatches)
    assert controls["base"]==controls["candidate"], "ordinary controls changed somewhere in the complete report"
    assert results["base"]>0 and results["candidate"]==0, results
    print("Two ordinary complete reports identical; expected counterexamples present only before patch.")
