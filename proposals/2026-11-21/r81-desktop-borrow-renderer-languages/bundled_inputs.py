"""Verify and list the actual shipped M150 catalog language inputs."""
import hashlib
import json
import sys
from pathlib import Path

root, seal_path = map(Path, sys.argv[1:])
seal = json.loads(seal_path.read_text())
assert seal["tree_format"] == "r64-assembler-json-rows-v1"
targets = []
for p in sorted(root.rglob("*")):
    rel = str(p.relative_to(root))
    if p.is_symlink():
        targets.append([rel, "link", str(p.readlink())])
    elif p.is_file():
        targets.append([rel, "x" if p.stat().st_mode & 0o111 else "-", hashlib.sha256(p.read_bytes()).hexdigest()])
digest = hashlib.sha256(json.dumps(targets,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
assert seal["components"]["extensions"]["source_tree_sha256"] == digest
assert seal["components"]["extensions"]["source_entries"] == len(targets)

seen = {}
for manifest in sorted((root/"packages").glob("*/extension.json")):
    raw = manifest.read_bytes()
    data = json.loads(raw)
    languages = data["surfaces"].get("content", {}).get("languages", [])
    if languages:
        assert data["id"] == manifest.parent.name
        seen[data["id"]] = languages
        print(f'BUNDLED {data["id"]} {json.dumps(languages,ensure_ascii=False,separators=(",",":"))} sha256={hashlib.sha256(raw).hexdigest()}')
assert seen == {"json-render":["json-render","svg"], "markdown-render":["md","markdown"], "mermaid-render":["mermaid"]}
print(f"PASS sealed Extensions {digest}; five registrations across three bundled contributors")
