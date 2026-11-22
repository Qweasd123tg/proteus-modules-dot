"""Run the exact changed side and row-span projection, with GPUI effects modeled."""
from pathlib import Path
import shutil
import sys

tier, out, packet = map(Path, sys.argv[1:])
dst = out / "src"
dst.mkdir(parents=True)
path = tier / "src/ui/diff/syntax.rs"
source = path.read_text()
enter = "    let mut source = String::new();\n"
leave = "    let path = if old {\n"
start = "        let start = source.len();\n"
end = "        ranges[index] = Some(start..source.len());\n"
assert all(source.count(x) == 1 for x in (enter, leave, start, end))
snippet = source.split(start)[1].split(end)[0]
if "fn append_expanded(" in source:
    assert snippet == "        append_expanded(&mut source, &line.text);\n"
    isolated = "    append_expanded(source, line);\n"
else:
    assert snippet == """        source.push_str(&line.text.replace('\\t', "    "));\n"""
    isolated = """    source.push_str(&line.replace('\\t', "    "));\n"""
# Keep source changes to two inert observation seams and a test-only wrapper of
# the exact appended statement. Production code and source hashes are separate.
adopted = source.replace(enter, "    crate::count::start();\n" + enter).replace(
    leave, "    crate::remember_ranges(&ranges);\n" + leave)
(dst / "syntax.rs").write_text(adopted + """
pub(super) fn isolated_append(source: &mut String, line: &str) {
""" + isolated + "}\n")
shutil.copytree(tier / "crates/diff", out / "crates/diff", symlinks=True)
shutil.copyfile(tier / "LICENSE-GPL", out / "LICENSE-GPL")
for source, target in (("probe.rs","src/main.rs"),("count.rs","src/count.rs"),
                       ("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock")):
    shutil.copyfile(packet / source, out / target)
