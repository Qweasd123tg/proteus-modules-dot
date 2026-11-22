"""Include the real formatter and an exact approval-display function over an inert DTO."""
from pathlib import Path
import shutil
import sys

tier, out, packet = map(Path, sys.argv[1:])
src=out/"src"
src.mkdir(parents=True)
shutil.copytree(tier/"src/tool_display", src/"tool_display", symlinks=True)
for a,b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),
            ("cases.rs","src/cases.rs"),("count.rs","src/count.rs")):
    shutil.copyfile(packet/a,out/b)
req=(tier/"src/ui/chat/requests.rs").read_text()
key=next(s for s in req.splitlines() if s.startswith("const JUSTIFICATION: "))
body=req.split("fn approval_body(",1)[1].split("\n/// Ways to allow",1)[0]
(src/"lib.rs").write_text("""
#![cfg(test)]
mod tool_display;
mod cases;
mod count;

use serde_json::Value;
struct AppApprovalRequest { call: Call, preview: Option<Preview> }
struct Call { name: String, args: Value }
struct Preview { body: Option<String> }
"""+key+"\nfn approval_body("+body)
