"""Generate the exact source-pruned no-window transport client used for measurements.
python prepare_narrow_client.py CLEAN_PINNED_DESKTOP CLEAN_CORE_AT_DESKTOP_DTO_PIN NEW_CLIENT_DIR
Build with cargo build --release and use target/release/clientbench as PERF6_CLIENT.
"""
from pathlib import Path
import argparse,shutil,subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('desktop',type=Path);p.add_argument('dto',type=Path);p.add_argument('dest',type=Path);a=p.parse_args()
d=a.dest;d.mkdir(exist_ok=False);(d/'api').mkdir()
def pin(src,rev):assert subprocess.check_output(['git','-C',src,'rev-parse','HEAD'],text=True).strip()==rev
pin(a.desktop,'210cc9f274ffe40533b390a0d9e940f251a9fa22');pin(a.dto,'105f8253f43a62b0f5025d99e2d4ccdcb322e34c')
def lines(p,start,end):return '\n'.join(p.read_text().splitlines()[start-1:end])
api=a.desktop/'src/api/mod.rs'
(d/'api/mod.rs').write_text('\n'.join(lines(api,b,e) for b,e in [(1,6),(21,21),(25,25),(27,60),(70,91),(316,344)])+'\n}\n')
for f in ('proxy','transport'):shutil.copyfile(a.desktop/f'src/api/{f}.rs',d/f'api/{f}.rs')
shutil.copyfile(a.desktop/'src/startup_trace.rs',d/'startup_trace.rs')
origin=a.desktop/'crates/client-common/src/lib.rs'
(d/'origin.rs').write_text(lines(origin,1,4)+'\n'+lines(origin,10,36)+'\n')
c=a.dto/'crates/proteus-contracts/src';l=lambda x,b,e:lines(c/x,b,e)+'\n'
(d/'types.rs').write_text('pub mod domain {use serde::{Serialize,Deserialize};use std::path::PathBuf;use uuid::Uuid;\n'+l('domain/ids.rs',26,29)+l('domain/image.rs',46,55)+'}\npub mod contracts { use uuid::Uuid;use serde::{Serialize,Deserialize};\n'+l('contracts/tool_terminal.rs',75,81)+'}\npub mod model_standard {use serde::{Serialize,Deserialize};\n'+l('model_standard/content_part.rs',20,25)+'}\npub mod app_protocol {\n'+(c/'app_protocol/transcript.rs').read_text()+'\n}\n')
main=(Path(__file__).resolve().parent/'client_main.rs').read_text().replace('mod api;','extern crate self as proteus_client_common;\ninclude!("origin.rs");\nextern crate self as proteus_contracts;\ninclude!("types.rs");\nmod api;');(d/'main.rs').write_text(main)
(d/'Cargo.toml').write_text("""[package]
name="perf6-client-exact-subset"
version="0.1.0"
edition="2024"
[[bin]]
name="clientbench"
path="main.rs"
[dependencies]
ureq={version="3",default-features=false,features=["json"]}
url="2"
anyhow="1"
serde={version="1",features=["derive"]}
serde_json="1"
uuid={version="1",features=["v4","serde"]}
""")
shutil.copyfile(Path(__file__).resolve().parent/'client.lock',d/'Cargo.lock')
