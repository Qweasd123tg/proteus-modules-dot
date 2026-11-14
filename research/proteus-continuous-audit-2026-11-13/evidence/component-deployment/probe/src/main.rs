#![allow(dead_code,unused_imports)]
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
pub(crate) fn proteus_binary() -> PathBuf {
    if let Some(path) = std::env::var_os("PROTEUS_BIN") {
        return path.into();
    }
    std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|dir| dir.join("proteus")))
        .filter(|path| path.is_file())
        .unwrap_or_else(|| PathBuf::from("proteus"))
}

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
