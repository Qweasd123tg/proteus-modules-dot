from pathlib import Path
import subprocess,hashlib,json,argparse
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--desktop',type=Path,required=True)
DESKTOP=parser.parse_args().desktop.resolve()
PROBE=ROOT/'probe'; SRC=PROBE/'src'; SRC.mkdir(parents=True,exist_ok=True)
hashes={}
def source(path):
    b=subprocess.check_output(['git','show','HEAD:'+path],cwd=DESKTOP)
    hashes[path]=hashlib.sha256(b).hexdigest()
    return b.decode()
def write(path,s):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(s)
write(PROBE/'Cargo.toml','''[package]
name="component-deployment-inventory-probe"
version="0.0.0"
edition="2024"
[workspace]
[dependencies]
anyhow="1"
serde={version="1",features=["derive"]}
serde_json="1"
''')
write(SRC/'inventory.rs',source('src/catalog/inventory.rs'))
write(SRC/'open.rs',source('src/catalog/open.rs'))
schema=source('src/catalog/schema.rs')
kind=schema[schema.index('#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]'):schema.index('impl Kind')]
checks=schema[schema.index('pub fn slug('):schema.index('pub fn directory(')]
write(SRC/'schema.rs','use std::path::{Path,Component};\nuse anyhow::{Result,ensure};\nuse serde::{Serialize,Deserialize};\n'+kind+checks)
backend=source('src/backend.rs')
backend=backend[backend.index('pub(crate) fn proteus_binary()'):backend.index('\nfn spawn_reader(')]
component=source('src/ui/settings/catalog/component.rs')
selection=component[component.index('        let previous_command ='):component.index('        let request =')]
# Selection logic verbatim from production. Supporting snapshot/receipt types below
# are minimal data-only substitutes, with unrelated GUI/runtime APIs omitted.
write(SRC/'selection.rs','''use std::path::Path;
use crate::{Installed,Target,Snapshot,ComponentReplacement};
use crate::catalog::{inventory::Inventory,open::OFFICIAL};
pub struct Catalogs { pub inventory: Inventory }
pub struct Selection { pub snapshot: Snapshot, pub catalogs: Catalogs }
impl Selection {
    fn snapshot(&self)->Option<&Snapshot>{Some(&self.snapshot)}
    pub fn replacements(&self, installed:&Installed, previous:Option<&Installed>) -> Vec<ComponentReplacement> {
        let Target::Component {command,exports:_,..}=&installed.target;
'''+selection+'''        replace
    }
}
''')
write(SRC/'main.rs',r'''#![allow(dead_code,unused_imports)]
use std::path::{Path,PathBuf};
use serde::{Serialize,Deserialize};
mod schema;
mod inventory;
mod open;
mod selection;
#[derive(Clone)] pub struct Source {pub url:String,pub branch:Option<String>}
mod catalog {pub(crate) use crate::{Source,schema,inventory,open};}
#[derive(Deserialize)] pub struct Plugin {pub id:String,pub command:String}
#[derive(Deserialize)] pub struct Snapshot {pub plugins:Vec<Plugin>}
pub enum Target {Component {command:Vec<String>,exports:std::collections::BTreeMap<String,Vec<String>>}}
pub struct Installed {pub source:Source,pub kind:schema::Kind,pub entry:String,pub target:Target}
#[derive(Serialize)] pub struct ComponentReplacement {pub id:String,pub command:String,pub expected_executable:Option<PathBuf>}
mod backend {
use std::path::PathBuf;
'''+backend+r'''
}
// Only extension discovery is stubbed: this probe exclusively checks modules;
// both bundled/user extension roots are absent in these isolated fixtures.
mod declarative {pub mod manifest {
use std::path::{Path,PathBuf};
pub struct Manifest {pub id:String}
pub struct Installed {pub manifest:Manifest,pub dir:PathBuf}
pub struct Problem {pub dir:PathBuf,pub error:String}
pub fn bundled_root()->PathBuf{PathBuf::from("/nonexistent-fixture-extensions")}
pub fn root()->Option<PathBuf>{None}
pub fn discover_sources(_: &Path,_:Option<&Path>)->(Vec<Installed>,Vec<Problem>){(vec![],vec![])}
}}
fn main(){
 let args=std::env::args().skip(1).collect::<Vec<_>>();
 let snapshot:Snapshot=serde_json::from_str(&std::fs::read_to_string(&args[0]).unwrap()).unwrap();
 let inventory=inventory::Inventory::local();
 let present=inventory.find(&open::OFFICIAL[0].source(),schema::Kind::ProcessModule,"memory-pack").map(|p|p.path.display().to_string());
 let installed=Installed {source:open::OFFICIAL[0].source(),kind:schema::Kind::ProcessModule,entry:"memory-pack".into(),target:Target::Component {command:vec![args[1].clone()],exports:std::collections::BTreeMap::new()}};
 let selection=selection::Selection {snapshot,catalogs:selection::Catalogs{inventory}};
 let replacements=selection.replacements(&installed,None);
 println!("{}",serde_json::json!({"module_inventory_path":present,"replace":replacements}));
}
'''.replace('mod schema;','pub mod schema;').replace('mod inventory;','pub mod inventory;').replace('mod open;','pub mod open;'))
(ROOT/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
