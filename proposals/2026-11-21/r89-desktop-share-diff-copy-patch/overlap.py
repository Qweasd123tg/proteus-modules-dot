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
    (79, 403, "27a8bd97bfe5dde85c947db9f09f097f7c634b97cd3276ba4d2a73a717264453", "31ce7c69b1ad9ee042d07422b17151365149966ef36cbe645a683343155860bd"),
    (81, 405, "4bcd3cc200a4b68aa778d6c6874516fe9aeb7b3a0daff9b86a6b0bd1462460d2", "826c81dbe915f2b26982aa76236350034feb8cd65975e1fd0168897c8fc4ebc0"),
    (83, 407, "8d1a965e6d831fd67186a341c7e674c1c2e016d5062986535db9bd5b440f4b30", "2005d81027637d92178ed92db2d905cce4d8a54ca7d3c14a2df62690dd15e46c"),
    (84, 408, "191549d92291d052d79b8493c992200bba8a23a73677f82468b8a7566fb1e4f7", "5cb36e1c8af665d2fc729a2631ba82b0bfebb308609eda17fd3ed98e4ce275d6"),
    (86, 410, "d455e394c0b00de666256060461789079d195e9ab6000325ece69256bc22e161", "a4dde43ec5562773ec2d1f6545ae7af61a77b23063c8bfe1449321391c2f629f"),
    (87, 411, "2f973e92c5d323c9145c3dbc3729e4246f9260ad39ec508ff102a27267e4cca1", "1f7e5766103307df29c70f6c9abf18831040b4250673b8fb6aa58f5c9cf3c815"),
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
    changed = re.findall(r"^(?:\+\+\+ b/|--- a/)((?:crates/diff/src/(?:lib|parse|tests)|src/ui/diff/file)\.rs)$", contents(path).decode(), re.M)
    if changed:
        hits.append((n, sorted(set(changed))))
assert sorted(hits) == [(n, ["crates/diff/src/lib.rs","crates/diff/src/tests.rs"]) for n in (245,264)], hits
print(f"PASS {len(entries)} previous Desktop patch hashes; shared files {hits}")
