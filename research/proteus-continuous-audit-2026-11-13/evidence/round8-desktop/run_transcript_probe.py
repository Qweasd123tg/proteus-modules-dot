#!/usr/bin/env python3
"""Re-extract production code and run isolated row identity + copy probes."""
from pathlib import Path
import hashlib, os, subprocess
OUT=Path(__file__).resolve().parent
DESKTOP=Path(os.environ.get('DESKTOP_ROOT','/workspace/scratch/3ba0fff8d310/desktop-behaviour'))
CORE=Path(os.environ.get('CORE_ROOT','/workspace/shared/history-events-audit'))
P=OUT/'transcript-probe'
for repo in [DESKTOP, CORE]:
    print(repo.name, subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),flush=True)
s=(CORE/'crates/proteus-core/src/app_server/transcript.rs').read_text()
start=s.index('pub(super) fn transcript_messages')
end=s.index('\n#[cfg(test)]\nmod tests',start)
rows=(CORE/'crates/proteus-core/src/app_server/transcript/rows.rs').read_text().replace('#[cfg(test)]\nmod tests;\n','')
prefix='''use serde_json::Value;
use crate::{domain::{Citation, HostedToolActivity, HostedToolStatus, ToolCall, ToolResult}, model_standard::{CanonicalMessage, CanonicalPart, ContentPart, MessageRole}};
pub use proteus_contracts::app_protocol::{AppTranscriptMessage, AppTranscriptSubagent, AppTranscriptTool};
'''
(P/'src/core_projection.rs').write_text(prefix+'mod rows {\n'+rows+'\n}\nuse rows::TranscriptRows;\n'+s[start:end])
s=(DESKTOP/'src/ui/chat/turn_copy.rs').read_text()
s=s[:s.index('\nimpl Plan {')].replace('use super::Chat;','').replace('    api::Api,','')
(P/'src/copy_probe.rs').write_text(s+(OUT/'copy-probe-fixture.rs').read_text())
(P/'src/lib.rs').write_text(f'''#![allow(dead_code, unused_imports)]
pub use proteus_contracts::{{domain, model_standard}};
pub mod agents {{ #[path = "{DESKTOP}/src/agents/codex/mod.rs"] pub mod codex; }}
#[path = "{DESKTOP}/src/transcript/mod.rs"] mod transcript;
mod core_projection;
#[cfg(test)] mod audit;
#[cfg(test)] mod copy_probe;
''')
manifest=(P/'Cargo.toml').read_text()
import re
manifest=re.sub(r'proteus-codex-client = \{ path = "[^"]+" \}',f'proteus-codex-client = {{ path = "{DESKTOP}/crates/codex-client" }}',manifest)
(P/'Cargo.toml').write_text(manifest)
for path in [DESKTOP/'src/transcript/mod.rs', DESKTOP/'src/ui/chat/turn_copy.rs',CORE/'crates/proteus-core/src/app_server/transcript.rs']:
    print(path.name,hashlib.sha256(path.read_bytes()).hexdigest(),flush=True)
subprocess.run(['cargo','test','--manifest-path',str(P/'Cargo.toml'),'--offline','round8_','--','--nocapture','--test-threads=1'],check=True)
