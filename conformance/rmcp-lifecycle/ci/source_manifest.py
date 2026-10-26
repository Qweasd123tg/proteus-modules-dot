"""Hash authored source/gate bytes before execution; no test or network activity."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = [root / name for name in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")]
for directory in ("src", "tests", "fixtures", "ci"):
    files.extend(path for path in (root / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
print(json.dumps({
    "scope": "authored package source and CI gate; not external source authority",
    "files": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(files)},
}, indent=2))
