"""Isolate actual Desktop catalog callbacks and the exact tabs crate."""
import hashlib
from pathlib import Path
import sys
import shutil

source, arm, here = map(Path,sys.argv[1:])
s=source/"src"
d=arm/"src"
ui=d/"ui"
ui.mkdir(parents=True,exist_ok=True)
for name,dst in {
    "harness.toml":"Cargo.toml", "harness.lock":"Cargo.lock",
    "probe.rs":"src/main.rs","carrier.rs":"src/ui/mod.rs",
    "cases.rs":"src/ui/cases.rs","ledger.rs":"src/ledger.rs",
}.items():
    shutil.copyfile(here/name,arm/dst)
shutil.copytree(source/"crates/tabs",arm/"crates/tabs",symlinks=True)
for name in ("attention.rs","conversations.rs"):
    shutil.copyfile(s/name,d/name)
(d/"agents/codex").mkdir(parents=True,exist_ok=True)
shutil.copyfile(s/"agents/codex/types.rs",d/"agents/codex/types.rs")
(d/"agents/codex/mod.rs").write_text("mod types; pub use types::{Summary,Model};\n")

def cut(text,a,b):
    start=text.index(a);return text[start:text.index(b,start+len(a))]
def fn(text,a,indent=""):
    start=text.index(a);end=text.index("\n"+indent+"}\n",start)+3+len(indent)
    return text[start:end]

chats=(s/"ui/chats.rs").read_text()
tab_ui=(s/"ui/tabs/mod.rs").read_text()
callbacks=cut(chats,"    pub(super) fn set_sessions(", "    /// Drops chats")
start="                        let known: std::collections::HashSet<_>"
stop="                        this.sessions_arrived"
focus=cut(callbacks,start,stop)
fmt=".map(|session| tabs::chat(&session.session_dir))"
if fmt in focus:
    assert callbacks.count(fmt)==1
    projected=callbacks.replace(fmt,".map(|session| crate::ledger::prefixed(&session.session_dir))",1)
else:
    fmt=".map(|session| session.session_dir.to_string_lossy())"
    assert callbacks.count(fmt)==1
    projected=callbacks.replace(fmt,".map(|session| crate::ledger::lossy_suffix(&session.session_dir))",1)
update_tabs=fn(tab_ui,"    pub(super) fn update_tabs(","    ")
available=fn(tab_ui,"pub(super) fn tab_available(")
(ui/"catalog.inc.rs").write_text("impl Workspace {\n"+projected+update_tabs+"}\n")
# Keep module-relative terminal, readonly, extension hooks exactly in place.
(ui/"avail.rs").write_text("use super::{App, tabs, extensions};\n"+available)
api=(s/"api/mod.rs").read_text()
for label,value in (
    ("catalog-admit-generation",callbacks.split("                        // Match the same lossy text",1)[0].split(start,1)[0]),
    ("catalog-commit-rerun",callbacks[callbacks.index(stop):]),
    ("layout-update",update_tabs),
    ("tab-availability",available),
    ("sessions-http-wrapper",fn(api,"    pub fn sessions(","    ")),
    ("activity", (s/"attention.rs").read_text()),
    ("conversation-projection",(s/"conversations.rs").read_text()),
):
    print(f"{hashlib.sha256(value.encode()).hexdigest()}  {label}")
