#![allow(dead_code)]
// The complete preferences, shortcuts, recent and session-mark production modules
// are included unchanged. Unused transport/catalog schemas are local stand-ins;
// the fields participating in the repro (tabs, theme and view) are real.
use proteus_tabs as tabs;
const APP_ID:&str="dev.proteus.native";
#[path="../../../../src/preferences.rs"] mod preferences;
#[path="../../../../src/shortcuts.rs"] mod shortcuts;
#[path="../../../../src/recent.rs"] mod recent;
#[path="../../../../src/sessions.rs"] mod sessions;
mod launch {pub enum Target{Spawn{profile:Option<String>},Attach{origin:String,token:String}}}
mod conversations{
 use serde::{Deserialize,Serialize};
 #[derive(Clone,Copy,Debug,Default,PartialEq,Eq,Serialize,Deserialize)]
 #[serde(rename_all="snake_case")] pub enum AgentKind {#[default]Proteus,Codex}
 #[derive(Clone,Debug,Default,PartialEq,Eq,Serialize,Deserialize)]
 #[serde(default,deny_unknown_fields)] pub struct CodexSelection {pub model:String,pub effort:Option<String>}
 #[derive(Clone,Debug,Default,PartialEq,Eq,Serialize,Deserialize)]
 #[serde(default,deny_unknown_fields)] pub struct CodexSelections{pub last:Option<CodexSelection>,pub threads:std::collections::BTreeMap<String,CodexSelection>,pub recent:Vec<String>}
 #[derive(Clone,Debug)] pub struct ConversationSummary{pub key:proteus_tabs::ChatKey,pub parent:Option<proteus_tabs::ChatKey>,pub workspace_path:std::path::PathBuf,pub updated_at_ms:Option<u64>,pub preview:Option<String>}
}
mod catalog{
 use serde::{Deserialize,Serialize};
 #[derive(Clone,Debug,Default,PartialEq,Serialize,Deserialize)]
 #[serde(default,deny_unknown_fields)] pub struct Preferences{pub sources:Vec<serde_json::Value>,pub installed:Vec<serde_json::Value>,pub official_sources_initialized:bool}
}
fn main(){
 use tabs::{TabLayout,ChatSpaces,Edge};
 let dir=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().join("restart-fixture").join(std::process::id().to_string());
 // This single-threaded fixture changes only its own process environment.
 unsafe{std::env::set_var("XDG_CONFIG_HOME",&dir)};
 let mut l=TabLayout::default();
 for id in ["files:a","files:b","files:c","files:d"] {l.open(id, |_|false);}
 l.split("files:b",l.pane_of("files:a").unwrap(),Edge::Bottom);
 l.split("files:c",l.pane_of("files:b").unwrap(),Edge::Right);
 l.split("files:d",l.pane_of("files:b").unwrap(),Edge::Bottom);
 l.lock_pane(l.pane_of("files:b").unwrap(),true,1200.,900.,5.);
 l.close("files:d");
 assert!(l.validate().is_ok());
 let mut p=preferences::Preferences::default();p.theme=preferences::ThemePreference::Light;p.view.scale=125;
 p.tabs=ChatSpaces::from_layout(l.clone());preferences::save(&p).unwrap();
 let control=preferences::load().unwrap();assert_eq!(control.view.scale,125);assert_eq!(control.theme,preferences::ThemePreference::Light);
 println!("valid-layout save/load control: Light, scale=125 retained");
 // Same pre-change retain as Workspace::update_tabs; unchanged available docs.
 l.retain(|_|true);l.close("files:c");
 let mut drawn=l.clone();drawn.retain(|_|true);
 println!("live layout validation = {:?}; render clone = {:?}",l.validate(),drawn.validate());
 assert!(l.validate().is_err());assert!(drawn.validate().is_ok());
 p.tabs=ChatSpaces::from_layout(l);preferences::save(&p).unwrap();
 let result=preferences::load();assert!(result.is_err());
 println!("first restart: {:#}",result.unwrap_err());
 let moved=std::fs::read_dir(dir.join(APP_ID)).unwrap().map(|f|f.unwrap().file_name().to_string_lossy().to_string()).collect::<Vec<_>>();
 assert!(moved.iter().any(|n|n.starts_with("preferences.json.broken-")));
 println!("preserved backup = {moved:?}");
 let defaults=preferences::load().unwrap();assert_eq!(defaults.view.scale,100);assert_eq!(defaults.theme,preferences::ThemePreference::Dark);assert!(defaults.tabs.is_empty());
 println!("next load: defaults Dark, scale=100, tabs empty");
 println!("fixture {}",dir.display());
}
