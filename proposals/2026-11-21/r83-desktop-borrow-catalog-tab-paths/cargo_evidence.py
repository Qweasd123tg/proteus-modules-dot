"""Select the one exact fresh binary reported by Cargo and run it."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from sys import argv

stamp, root, message_path, output, work, patch = argv[1:]
root, message_path, output, work, patch = map(Path, (root, message_path, output, work, patch))
root = root.resolve()

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def inputs():
    files = [root / "Cargo.toml", root / "Cargo.lock", *[p for p in (root / "src").rglob("*") if p.is_file()], *[p for p in (root / "crates").rglob("*") if p.is_file()]]
    return {file.relative_to(root).as_posix(): digest(file) for file in sorted(files)}

def tool(name, args):
    launcher = Path(shutil.which(name)).resolve(strict=True)
    version = subprocess.check_output([str(launcher), *args], text=True).splitlines()[0]
    return {"version": version, "launcher_sha256": digest(launcher)}

messages = [json.loads(line) for line in message_path.read_text().splitlines() if line]
name = "desktop-catalog-tab-id-probe"
matches = []
for obj in messages:
    if obj.get("reason") != "compiler-artifact":
        continue
    target = obj.get("target", {})
    if target.get("name") != name or target.get("kind") != ["bin"]:
        continue
    if Path(obj["manifest_path"]).resolve() == root / "Cargo.toml":
        matches.append(obj)
assert len(matches) == 1, (stamp, len(matches))
selected = matches[0]
target = selected["target"]
assert selected["fresh"] is False
assert selected["profile"]["test"] is False and target["crate_types"] == ["bin"]
assert Path(target["src_path"]).resolve(strict=True) == root / "src/main.rs"
exe = Path(selected["executable"]).resolve(strict=True)
warm = Path(os.environ["CARGO_TARGET_DIR"]).resolve(strict=True)
assert exe == warm / "debug" / name
end = [x for x in messages if x.get("reason") == "build-finished"]
assert len(end) == 1 and end[0]["success"] is True

tabs = [record for record in messages
        if record.get("reason") == "compiler-artifact"
        and record.get("target", {}).get("name") == "proteus_tabs"
        and Path(record["manifest_path"]).resolve() == root/"crates/tabs/Cargo.toml"]
assert len(tabs)==1
tab = tabs[0]
assert tab["fresh"] is False and tab["target"]["kind"]==["lib"] and tab["profile"]["test"] is False
assert Path(tab["target"]["src_path"]).resolve(strict=True)==root/"crates/tabs/src/lib.rs"
tab_files = [Path(name).resolve(strict=True) for name in tab["filenames"]]
assert any(path.suffix==".rlib" for path in tab_files)
def local_library():
    return {path.relative_to(warm).as_posix():digest(path) for path in tab_files}
tabs_before=local_library()
bound = inputs()
sha_before = digest(exe)
with output.open("wb") as stdout, work.open("wb") as stderr:
    subprocess.run([str(exe)], cwd=root, stdout=stdout, stderr=stderr, check=True)
sha_after = digest(exe)
assert sha_before == sha_after and inputs() == bound and local_library()==tabs_before
assert ("ARM " + stamp) in work.read_text().splitlines()
record = {
    "arm": stamp,
    "manifest": "Cargo.toml",
    "source": "src/main.rs",
    "target": name,
    "executable_from_warm_target": exe.relative_to(warm).as_posix(),
    "bin": True,
    "test": False,
    "fresh": False,
    "executable_sha256_before": sha_before,
    "executable_sha256_after": sha_after,
    "trace_sha256": digest(output),
    "production_patch_sha256": digest(patch),
    "inputs_sha256": bound,
    "native_free_local_tabs": {"manifest":"crates/tabs/Cargo.toml", "source":"crates/tabs/src/lib.rs", "fresh":False, "output_sha256_before_and_after":tabs_before},
    "cargo": tool("cargo", ["--version"]),
    "rustc": tool("rustc", ["--version"]),
}
print("ARTIFACT " + json.dumps(record, sort_keys=True, separators=(",", ":")))
