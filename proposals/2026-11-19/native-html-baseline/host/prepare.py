"""Reproduce the scoped GPUI tests using the exact production constructor expression."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

here = Path(__file__).resolve().parent
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("desktop",type=Path)
p.add_argument("out",type=Path)
p.add_argument("--patch",type=Path)
a = p.parse_args()
desktop = a.desktop.resolve()
root = a.out.resolve()
root.mkdir(parents=True,exist_ok=False)
source = root/"source"
caller = Path("src/ui/extensions/declarative/rich_text.rs")
base = Path("vendor/gpui-base")
for name,want in {
    caller:"d4090e5743a7bd4a6bf46eacbdaf7b003f306dd5",
    base/"src/text/state.rs":"a590e391d4ffa62076ee66e91e5cf6bcda530817",
    base/"src/text/markdown_ext.rs":"f04215c855dfb2a48cb0c9df2908a3ff4e3ff8be",
}.items():
    data=(desktop/name).read_bytes()
    assert hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()==want,name
(source/caller).parent.mkdir(parents=True)
shutil.copyfile(desktop/caller, source/caller)
shutil.copytree(desktop/base, source/base)
if a.patch:
    patch=a.patch.read_bytes()
    assert hashlib.sha256(patch).hexdigest()=="a5bd0504829a4f3716c81928ca54a8fa1d48a26145c17807434926bbe9f1d6e6"
    subprocess.run(["patch","-p1"],input=patch,cwd=source,check=True)
    method="html_for_replacements"
else:
    method="html"
text=(source/caller).read_text()
expr = re.findall(r"let state = cx\.new\(\|cx\| (TextViewState::[a-z_]+\(html, cx\)\.scrollable\(false\))\);",text)
assert expr==[f"TextViewState::{method}(html, cx).scrollable(false)"], expr
(root/"factory.in").write_text(expr[0]+"\n")
subprocess.run([sys.executable,here/"observe.py",source/base],check=True)
(root/"src/bin").mkdir(parents=True)
for name in ("main.rs","heap.rs"):
    shutil.copyfile(here/name,root/"src"/name)
for name in ("liveprobe.rs","pushcounts.rs"):
    shutil.copyfile(here/name,root/"src/bin"/name)
(root/"Cargo.toml").write_text(f"""[package]
name="state-qual"
version="0.1.0"
edition="2024"
[dependencies]
gpui-base={{path="source/vendor/gpui-base", features=["test-support","gpui-fast"]}}
gpui={{package="gpui-fast",version="=0.1.12",default-features=false,features=["test-support"]}}
serde_json="1"
[patch.crates-io]
gpui-fast={{path={json.dumps(str(desktop/"vendor/gpui-fast"))}}}
gpui-fast-wgpu={{path={json.dumps(str(desktop/"vendor/gpui-fast-wgpu"))}}}
[features]
scoped=[]
heap=[]
""")
lock=(here/"Cargo.lock").read_text()
# Unused optional gpui-fast-wgpu patch exists in the archived lockfile.
(root/"Cargo.lock").write_text(lock)
