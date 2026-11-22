"""Extract the exact production per-file clipboard chain from the native header."""
import hashlib
import shutil
import sys
from pathlib import Path

source, output, packet = (Path(x) for x in sys.argv[1:])
out = output / "src"
out.mkdir(parents=True)
shutil.copytree(source / "crates/diff", output / "crates/diff", symlinks=True)
for a, b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),("probe.rs","src/main.rs")):
    shutil.copyfile(packet / a, output / b)

def between(data,start,end):
    at=data.index(start)
    return data[at:data.index(end,at+len(start))]
file=(source/"src/ui/diff/file.rs").read_text()
view=(source/"src/ui/diff/mod.rs").read_text()
parse=(source/"crates/diff/src/parse.rs").read_text()
callback=between(file,"                            .disabled(file.patch.is_empty())","                    ),\n")
assert callback.strip().endswith("}),")
(out/"copy.inc.rs").write_text(
    "fn copy_button(file: Rc<File>, cx: &mut Context) -> Button {\n    Button::default()\n"+callback.rstrip().removesuffix(",")+"\n}\n"
    + ("fn cfg_shared(_: &File) -> bool { true }\n" if "patch.as_str().to_owned()" in callback
       else "fn cfg_shared(_: &File) -> bool { false }\n"))
for label, context in {
    "native-header-before-copy": file[:file.index(callback)],
    "native-header-after-copy": file[file.index(callback)+len(callback):],
    "full-copy-and-view-replacement": view,
    "binary-record-parsing-and-helpers": parse[parse.index("// Git can include forward and reverse records."):],
    "line-identity-and-hunks": between(parse,"        if binary.hide(line)", "    for file in &mut files {").split("\n    }\n",1)[0],
}.items():
    print(hashlib.sha256(context.encode()).hexdigest(), label)
