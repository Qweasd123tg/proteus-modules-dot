from pathlib import Path
import hashlib,json,shutil
out=Path(__file__).resolve().parent
root=out.parent if (out.parent/'src/ui/chats.rs').exists() else out/'source'
rec=[]
def extract(path,name):
 s=(root/path).read_text();a=s.index('fn '+name+'(');a=s.rfind('\n',0,a)+1;b=s.index('{',a);d=1;e=b+1
 while d:d+=(s[e]=='{')-(s[e]=='}');e+=1
 raw=s[a:e].strip();rec.append(dict(path=path,name=name,start=s[:a].count('\n')+1,end=s[:e].count('\n')+1,sha256=hashlib.sha256(raw.encode()).hexdigest()))
 return raw.replace('pub(super) ','pub ').replace('pub(in crate::ui) ','pub ')
def impls(path,names):return '\n'.join(extract(path,n) for n in names)
(out/'probe/src/generated.rs').write_text('''// GENERATED from recorded production method bodies. Only visibility is relaxed.\nimpl WindowGroup {\n'''+impls('src/ui/workspace/windows.rs',['set_core','has_core_connection','core_slot','server_stopped'])+'\n}\nimpl Workspace {\n'+impls('src/ui/chats.rs',['open_chat','insert_chat','sync_chats'])+'\n}\nimpl Chat {\n'+extract('src/ui/chat/mod.rs','new')+'\n'+extract('src/ui/chat/pump.rs','apply')+'\n}\nimpl Session{\n'+impls('src/ui/chat/session.rs',['stream_connected','stream_disconnected'])+'\n}\n'+extract('src/ui/workspace/drivers.rs','core')+'\n')
(out/'extraction.json').write_text(json.dumps(rec,indent=2)+'\n')
# Standalone source paths in probe point here. Preserve source file bytes.
source=out/'source'
if root!=source:
 for name in ['src/api','crates/client-common','crates/tabs']:
  shutil.copytree(root/name,source/name,dirs_exist_ok=True)
 for name in ['src/backend.rs','src/connection.rs','src/ui/workspace/windows.rs','src/ui/workspace/drivers.rs','src/ui/chats.rs','src/ui/chat/mod.rs','src/ui/chat/context_requests.rs','src/ui/chat/pump.rs','src/ui/chat/actions.rs','src/ui/chat/session.rs','src/ui/tabs/mod.rs','src/ui/workspace.rs','AGENTS.md','BUILDING.md','LICENSE-APACHE','LICENSE-GPL']:
  (source/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,source/name)
files={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
(out/'source-sha256.json').write_text(json.dumps(files,indent=2)+'\n')
(out/'probe/Cargo.toml').write_text('''[package]
name="desktop-reconnect-state-probe"
version="0.0.0"
edition="2024"
[workspace]
[dependencies]
proteus-tabs={path="../source/crates/tabs"}
proteus-client-common={path="../source/crates/client-common"}
proteus-contracts={git="https://github.com/Proteus-harness/Proteus-core.git",rev="5e8b6ae63fd6f50611129b19687b158621359706"}
url="2"
anyhow="1"
async-channel="2"
base64="0.22"
libc="0.2"
serde={version="1",features=["derive"]}
serde_json="1"
ureq={version="3",default-features=false,features=["json"]}
uuid={version="1",features=["v4"]}
[profile.dev]
debug=0
incremental=false
''')
