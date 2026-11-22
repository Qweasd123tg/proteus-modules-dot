"""Read the finite sealed Desktop proposal roster; hash every audited patch."""
import hashlib
import json
import re
import sys
from pathlib import Path

root, output = map(Path, sys.argv[1:])
roster = root / "r54/m100/manifest.json"
composition = root / "r64/m150-source/composition-receipt.json"

def contents(path):
    return path.read_bytes()

def sha(path):
    return hashlib.sha256(contents(path)).hexdigest()

def require(path, expected):
    assert sha(path) == expected, path
    return json.loads(contents(path))

m100 = require(roster, "4f1d0c89334708c65822befeadbf4c3eed81f17a0498a1a9fa22520ef0c46cd6")
m150 = require(composition, "d0525f96069002b70d3d60ac0d32c05253cff8801c61fc3fee58c8fb507cd3b2")
entries = [
    (int(number), roster.parent / m100["selected_patch_paths"][number], m100["selected_patch_sha256"][number])
    for number, component in m100["selected_sources"].items() if component == "desktop"
]
entries += [
    (row["n"], root / row["appliedSource"], row["patch_sha256"])
    for row in m150["additions"] if row["component"] == "desktop"
]
recent = [
    (68, 393, "f4211e874bcafbd3feec7813fc7e080f3d52ff64f4c08d997dbd3a97b0e2bc48", "87c96e53a64f765f60599998ffb0e9d0374b56e60e5f1bfc1827259d458e32ea"),
    (71, 396, "7b8956ceb0142e690a9bf56e8ede22091d809067a6f5947667b45f65f66e66e1", "7e15342d0cae2a391f91e45f86a61d28a212533caddaf161b969cae1be88ceef"),
    (73, 398, "cd1f568d1308cc160b7c186a8dd293705317f45f7c57615997e2a598ce154b88", "897d3a261fa0da254f324a8acad4d51c5f33019b83370734d9bc59c74c3943a0"),
    (75, 400, "74a7bab54e92ca61e5da4dfe2eb3b6c5894a93607e3e1a6162b1c566fb6b165a", "50bec985641b0231497394cf1f507f739464b93c975c4a95469ad9c34f1310aa"),
    (77, 401, "eabb4a355e104cc8c1113a5cc9e8d5ccb14a4b4f9c7f9b07e3ad280051481e52", "af9081a70781c52ab1cdd55435c4256c2e4abb49fb4a23c42794ef48b7edaa74"),
]
with output.open("w") as out:
    for round_, number, expected, patch in recent:
        row, = (row for row in require(root / f"r{round_}/published.json", expected) if row["n"] == number)
        assert row["component"] == "desktop"
        path = root / row.get("cumulativeSource", row["source"])
        entries.append((number, path, patch))
        print(path.resolve(), file=out)

hits = []
for n, path, expected in entries:
    assert sha(path) == expected, (n, path)
    changed = re.findall(r"^(?:\+\+\+ b/|--- a/)(src/ui/chat/(?:thread|stamp)\.rs)$", contents(path).decode(), re.M)
    if changed:
        hits.append((n, sorted(set(changed))))
        if n == 363:
            assert "let tools" in contents(path).decode()
            assert "stamp::" not in contents(path).decode()
assert hits == [(363, ["src/ui/chat/thread.rs"])], hits
print(f"PASS {len(entries)} sealed Desktop patch hashes; only #363 shares thread.rs (distant render header hunk), no overlapping stamp decision")
