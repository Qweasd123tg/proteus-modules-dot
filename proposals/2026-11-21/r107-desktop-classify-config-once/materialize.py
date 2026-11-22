"""Use the whole launcher catalog and native tests, with observation-only counters."""
from pathlib import Path
import shutil
import sys

tier,out,packet=map(Path,sys.argv[1:])
src=out/"src"
(src/"catalog").mkdir(parents=True)
catalog=tier/"src/ui/launcher/config/catalog.rs"
body=catalog.read_text()
def before(target, hit):
    global body
    assert body.count(target)==1, target
    lead=target[:len(target)-len(target.lstrip(" "))]
    note=f"{lead}crate::meter::bump(crate::meter::Hit::{hit});\n"
    body=body.replace(target,note+target)

if "let Ok(metadata) = path.metadata()" in body:
    before("        let Ok(metadata) = path.metadata() else {","Classify")
else:
    before("        if path.is_dir() {","Classify")
    assert body.count("&& path.is_file()")==1
    body=body.replace("&& path.is_file()","&& { crate::meter::bump(crate::meter::Hit::Classify); path.is_file() }")
original="path.canonicalize().ok()"
assert body.count(original)==1
body=body.replace(original,"{crate::meter::bump(crate::meter::Hit::CurrentCanon); "+original+"}")
for needle,hit in [
    ("    let physical = match directory.canonicalize() {","DirectoryCanon"),
    ("    let entries = match std::fs::read_dir(directory) {","DirectoryRead"),
    ("        *visited_entries += 1;","Entry"),
    ("            let Ok(physical) = path.canonicalize() else {","ConfigCanon"),
    ("    let limit = MAX_METADATA_BYTES.min(", "LabelAsked"),
    ("    let Some(mut file) = std::fs::File::open(path)","LabelOpened"),
]:
    before(needle,hit)
hit="    *bytes += data.len();"
assert body.count(hit)==1
body=body.replace(hit,"    crate::meter::add(crate::meter::Hit::LabelBytes,data.len());\n"+hit)
(src/"catalog.rs").write_text(body)
shutil.copyfile(catalog.parent/"catalog/tests.rs",src/"catalog/tests.rs")
(src/"lib.rs").write_text("#![cfg(test)]\nmod catalog; mod meter; mod cases;\n")
for a,b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),
            ("cases.rs","src/cases.rs"),("meter.rs","src/meter.rs")):
    shutil.copyfile(packet/a,out/b)
