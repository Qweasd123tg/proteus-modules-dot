from pathlib import Path
import sys

root = Path("src/ui/chat")
height = root / "history/height_key.rs"
arm = sys.argv[1]
text = height.read_text()
prefix = text[:text.index("#[cfg(test)]\nmod tests {")]
assert ("identity_hash(&session.key.tab_id(), id)" in prefix) == (arm == "candidate")
target = root / "history" / f"{arm}_key.rs"
target.write_text(prefix)

if arm == "candidate":
    session = (root / "session.rs").read_text()
    line = "snapshot_identity: Option<(SessionId, String)>,"
    assert line in session
    begin = session.index("    pub(super) fn durable_id(")
    end = session.index("\n    }\n", begin) + 7
    (root / "mod.rs").write_text(
        "use proteus_contracts::domain::SessionId;\n"
        "pub(crate) mod history;\n"
        "pub(crate) mod scroller;\n"
        "pub(crate) struct Session {\n"
        "    pub(crate) key: proteus_tabs::ChatKey,\n"
        f"    pub(crate) {line}\n"
        "}\nimpl Session {\n" + session[begin:end] + "\n}\n"
    )

    p = root / "scroller.rs"
    scroller = p.read_text()
    begin = scroller.index("pub(super) fn height_hash(")
    end = scroller.index("\n}\n", begin) + 3
    height_hash = scroller[begin:end]
    store = (root / "scroller/scrollbar/height_store.rs").read_text()
    at = store.index("pub(in super::super::super) struct Key {")
    end = store.index("\n}\n", at) + 3
    begin = store.rfind("#[derive(", 0, at)
    key = store[begin:end].replace("pub(in super::super::super) struct Key", "pub(crate) struct HeightCacheKey")
    alias = "pub(in super::super::super) type Hash = [u8; 32];"
    assert alias in store
    p.write_text("use sha2::{Digest, Sha256};\n" + alias.split(") ", 1)[1] + "\n" + key + "\n" + height_hash)
