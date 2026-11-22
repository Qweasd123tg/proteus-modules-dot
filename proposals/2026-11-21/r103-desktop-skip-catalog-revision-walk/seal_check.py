from pathlib import Path
import hashlib
import json
import sys

tree=Path(sys.argv[1])
seal=json.loads(Path(sys.argv[2]).read_text())
assert seal["tree_format"]=="r64-assembler-json-rows-v1"
component=sys.argv[3] if len(sys.argv)>3 else "desktop"
expected=seal["components"][component]
entries=[]
for item in sorted(tree.rglob("*")):
    name=str(item.relative_to(tree))
    if item.is_symlink():
        entries.append([name,"link",str(item.readlink())])
    elif item.is_file():
        entries.append([name,"x" if item.stat().st_mode&0o111 else "-",hashlib.sha256(item.read_bytes()).hexdigest()])
digest=hashlib.sha256(json.dumps(entries,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
assert digest==expected["source_tree_sha256"], (digest,expected)
assert len(entries)==expected["source_entries"]
lock=hashlib.sha256((tree/"Cargo.lock").read_bytes()).hexdigest()
assert lock==expected["lock_sha256"]
print(f"PASS sealed {component} source {digest} ({len(entries)} entries), Cargo.lock {lock}")
