"""Compile source slices over minimal non-GPUI carrier types; no production writes."""
import re
from pathlib import Path
from sys import argv

source, harness = map(Path, argv[1:])
def read(path):
    return (source / path).read_text()
def span(text, start, end):
    assert text.count(start) == 1, start
    a = text.index(start)
    return text[a:text.index(end, a)]
def match(text, pattern):
    found = re.findall(pattern, text, re.M)
    assert len(found) == 1, (pattern, found)
    return found[0]
def export(text):
    return text.replace("pub(in crate::ui)", "pub").replace("pub(super)", "pub")

chat = read("src/ui/chat/session.rs")
ctx = read("src/ui/chat/context_usage.rs")
act = read("src/ui/chat/actions.rs")
adapter = read("src/ui/extensions/session.rs")
context = read("src/ui/extensions/host/scope.rs")
host = read("src/ui/extensions/host.rs")
scopes = read("src/ui/extensions/declarative/runtime/scopes.rs")
manifest = read("src/declarative/manifest.rs")
protocol = read("src/declarative/protocol.rs")
fields = "\n".join(match(chat, rf"^(    pub {field}: [^\n]+,)$")
                     for field in ["connected","config","context","execution","pending"])
context_fields = export(span(ctx, "pub(in crate::ui) struct ContextUsage {", "\n\nimpl ContextUsage"))
config_assignment = match(act, r"^(        self.session.config = Some\(.*\);)$")
apply_step = config_assignment.replace("self.session.config", "session.config")
pure_state = export(span(adapter, "pub(in crate::ui) fn state(", "\n\npub(in crate::ui) fn entries("))
local_cmp = match(act, r"if (this\.config_generation != generation) \{")
remote_cmp = match(act, r"if (this\.config_generation == generation) \{")
(harness / "src/adapter.rs").write_text(f"""use crate::session;
use proteus_contracts::app_protocol::config::ConfigSummary;
use proteus_contracts::app_protocol::{{AppExecutionState, AppPendingRequests, AppSessionActivity}};
#[allow(unused_imports)]
use std::sync::Arc;
#[derive(Clone, Copy)]
{context_fields}
pub struct Session {{
{fields}
}}
pub fn accept_config(session: &mut Session, config: ConfigSummary) {{
{apply_step}
}}
struct Generation {{ config_generation: u64 }}
pub fn accepts_local(current: u64, generation: u64) -> bool {{
    let this = Generation {{ config_generation: current }};
    if {local_cmp} {{ return false; }}
    true
}}
pub fn accepts_discovered(current: u64, generation: u64) -> bool {{
    let this = Generation {{ config_generation: current }};
    {remote_cmp}
}}
{pure_state}
""")
known = span(scopes, "        let snapshot_known = self", "        let workspace =").strip()
announce = match(scopes, r"        if (self\.lifetime\.session\(\) && self\.extension\.manifest\.session_events && !snapshot_known) \{")
declared = export(span(context, "#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]\npub(in crate::ui) enum Lifetime", "\n\n#[derive(Clone, Copy, Debug, PartialEq"))
cursor = "#[derive(Default)]\n" + export(span(scopes, "pub(super) struct EventCursor(", "\n\npub(super) struct Scope"))
accepts = span(manifest, "    pub fn accepts_session_update(", "    /// Descriptive labels").replace("super::session::Update", "Update")
gate = match(scopes, r"if (this\s+\.extension\s+\.manifest\s+\.accepts_session_update\(&event\.update\)\s+&& this\.session_events\.admit\(event\.event_id\))")
copy = match(scopes, r"update: (event\.update\.clone\(\)),")
addressed = match(host, r"if (host\.session_dir\(cx\).as_ref\(\) == Some\(&event\.session_dir\)) \{")
supports = match(host, r"pub\(in crate::ui\) fn supports_core\(&self, cx: &App\) -> bool \{\s+(self\.session_dir\(cx\).is_some\(\))\s+\}")
outgoing = span(protocol, "    SessionSnapshot {", "    /// First message:")
tag = match(protocol, r'(#\[serde\(tag = "type", rename_all = "snake_case"\)\])\npub enum Outgoing')
(harness / "src/routes.rs").write_text(f"""use crate::session::Update;
use std::collections::BTreeMap;
use std::path::PathBuf;
{declared}
{cursor}
pub struct Manifest {{
    pub session_events: bool,
    pub session_entries: bool,
}}
impl Manifest {{
{accepts}
}}
struct Extension {{ manifest: Manifest }}
struct Scope {{ announced: bool, session: Option<PathBuf> }}
pub struct Runtime {{
    lifetime: Lifetime,
    extension: Extension,
    scopes: BTreeMap<String, Scope>,
    session_events: EventCursor,
}}
pub struct Event {{
    pub session_dir: PathBuf,
    pub event_id: u64,
    pub update: Update,
}}
pub struct Host(Option<PathBuf>);
impl Host {{
    pub fn new(path: Option<PathBuf>) -> Self {{ Self(path) }}
    fn session_dir(&self, _cx: &()) -> Option<PathBuf> {{ self.0.clone() }}
    pub fn supports_core(&self, cx: &()) -> bool {{ {supports} }}
}}
impl Runtime {{
    pub fn new(lifetime: Lifetime, session_events: bool, session_entries: bool) -> Self {{
        Self {{
            lifetime,
            extension: Extension {{ manifest: Manifest {{ session_events, session_entries }} }},
            scopes: BTreeMap::new(),
            session_events: EventCursor::default(),
        }}
    }}
    pub fn scope(&mut self, id: &str, announced: bool, session: Option<PathBuf>) {{
        self.scopes.insert(id.into(), Scope {{ announced, session }});
    }}
    pub fn should_snapshot(&self, context: &str, session: Option<PathBuf>) -> bool {{
        if !self.scopes.contains_key(context) {{ return false; }}
        {known}
        {announce}
    }}
    pub fn receive(&mut self, host: &Host, event: &Event) -> Option<Update> {{
        let cx = &();
        if !self.lifetime.session() || !host.supports_core(cx) {{ return None; }}
        if !({addressed}) {{ return None; }}
        let this = self;
        if {gate} {{
            Some({copy})
        }} else {{
            None
        }}
    }}
}}
#[derive(serde::Serialize)]
{tag}
pub enum Outgoing {{
{outgoing}
}}
""")
