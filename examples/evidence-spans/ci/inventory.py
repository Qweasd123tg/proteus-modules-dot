#!/usr/bin/env python3
"""Inventory only this increment's evidence leaf, excluding this manifest itself."""
import hashlib
import json
from pathlib import Path

root = Path("validation/evidence-spans")
entries = []
for path in sorted(root.rglob("*")):
    if path.name == "artifact-manifest.json":
        continue
    if path.is_symlink():
        raise ValueError("evidence must not contain symlinks")
    if path.is_file():
        data = path.read_bytes()
        entries.append({"path": path.relative_to(root).as_posix(), "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
(root / "artifact-manifest.json").write_text(json.dumps({
    "schema_version": 1, "scope": "this authored evidence-spans increment only",
    "files": entries, "self_excluded": "artifact-manifest.json"
}, indent=2) + "\n")
