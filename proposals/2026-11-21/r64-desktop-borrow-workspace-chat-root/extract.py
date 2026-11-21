from pathlib import Path
import sys

source, dest, arm = sys.argv[1:]
src = Path(source).read_text()
begin = src.index("fn resolve_space_root(")
code = src[begin:]
if arm == "stock":
    assert "seen.insert(current.key.clone())" in code
elif arm == "candidate":
    assert "seen.insert(&current.key)" in code
else:
    raise ValueError(arm)
Path(dest).write_text(
    "use std::collections::HashSet;\n"
    "use proteus_tabs::{self as tabs, ChatKey};\n"
    "use crate::conversations::ConversationSummary;\n"
    + "pub " + code
)
