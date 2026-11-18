#!/usr/bin/env python3
"""Native differential: exact Picker handler + pinned GPUI raw dispatch/keyboard click. No cargo."""
from pathlib import Path
import argparse, hashlib, subprocess, tempfile
ap = argparse.ArgumentParser()
ap.add_argument("before", type=Path); ap.add_argument("after", type=Path)
ap.add_argument("--rustc", default="rustc"); args = ap.parse_args()
def source(root, path, sha):
    buf = (root / path).read_bytes()
    assert hashlib.sha256(buf).hexdigest() == sha, f"unexpected {path}"
    return buf.decode()
def method(source, start):
    i = source.index(start); a = source.index("{",i); depth = 0
    for b in range(a, len(source)):
        if source[b] == "{": depth += 1
        if source[b] == "}":
            depth -= 1
            if not depth: return source[i:b+1]
    raise AssertionError(start)
w = source(args.before,"vendor/gpui-fast/src/window.rs","cf1a90f6b768d96ae172cd1b2b9566a409de25e0618edd93125bd5928a179a9d")
d = source(args.before,"vendor/gpui-fast/src/elements/div.rs","fa6378a65d066a46670dea1b65d305c25e2e7f06c1ced9f7a4175e1adb1aa8dc")
a = d.index("window.on_key_event({", d.index("// Record the focus generation at which an enter/space key"))
b = d.index("\n                }\n", a)
base = (Path(__file__).parent / "events.rs.in").read_text()
base = base.replace("/*DISPATCH*/", method(w, "fn dispatch_key_down_up_event("))
base = base.replace("/*BUTTON*/",d[a:b])
with tempfile.TemporaryDirectory() as td:
    for name,tree,sha in (("before", args.before, "7f649b23ab24ed631024c5de22a066d6f531ea3ff2402c916a0aad18fc8ba14c"), ("after",args.after,"548c7d0ea642586d811648a71ba79c4146b8aab46e2f92aa9dd5be850b7adcff")):
        picker = source(tree, "src/ui/picker.rs", sha)
        assert ".capture_key_down(cx.listener(Self::keys))" in picker
        native = base
        for token,sig in (("CURRENT","fn current("),("KEYS","fn keys("),("FOCUS","pub fn search_focus(")):
            native = native.replace(f"/*{token}*/",method(picker,sig))
        filename = Path(td)/f"{name}.rs"; filename.write_text(native)
        exe = filename.with_suffix("")
        subprocess.run([args.rustc,"--edition=2024","-Awarnings",str(filename),"-o",str(exe)],check=True)
        subprocess.run([str(exe), name],check=True)
