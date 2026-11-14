#![allow(dead_code)]
mod settings { pub mod draft; pub mod addons; pub mod mcp; }
use std::{fs,path::PathBuf};
use settings::{draft::Draft,mcp::{McpText,mcp_problems}};
use serde_json::json;
use proteus_contracts::app_protocol::config_builder::ConfigBuilderSnapshot;
fn main(){
 let args:Vec<_>=std::env::args().collect();let mode=&args[1];let root=PathBuf::from(&args[2]);
 let snapshot:ConfigBuilderSnapshot=serde_json::from_slice(&fs::read(root.join("snapshot.json")).unwrap()).unwrap();
 let baseline=Draft::from_snapshot(&snapshot);assert!(!baseline.mcp_enabled("db"));assert!(baseline.mcp_enabled("db2"));
 let mut direct=baseline.clone();direct.set_mcp_text(0,McpText::Name,"db20").unwrap();assert!(!direct.mcp_enabled("db20"));assert!(direct.mcp_enabled("db2"));
 let mut draft=baseline.clone();draft.set_mcp_text(0,McpText::Name,"db2").unwrap();assert_eq!(mcp_problems(&draft,None).len(),2);
 draft.set_mcp_text(0,McpText::Name,"db20").unwrap();assert!(mcp_problems(&draft,None).is_empty());
 assert!(draft.mcp_enabled("db20"));assert!(!draft.mcp_enabled("db2"));
 if mode=="direct" { draft=direct; }
 if mode=="undo" {
  draft.set_mcp_text(0,McpText::Name,"db2").unwrap();draft.set_mcp_text(0,McpText::Name,"db").unwrap();
  assert!(draft.is_dirty(&baseline));assert!(draft.mcp_enabled("db"));assert!(!draft.mcp_enabled("db2"));
  assert_eq!(draft.addons.mcp_servers,baseline.addons.mcp_servers);
 }
 let before:Vec<_>=baseline.addons.mcp_servers.iter().map(|s|json!({"name":s.name,"effective_enabled":baseline.mcp_enabled(&s.name)})).collect();
 let after:Vec<_>=draft.addons.mcp_servers.iter().map(|s|json!({"name":s.name,"effective_enabled":draft.mcp_enabled(&s.name)})).collect();
 println!("{}",json!({"request":draft.changes(&baseline),"before":before,"after":after,"final_validation_errors":mcp_problems(&draft,None).len(),"direct_rename_preserves_switches":true,"dirty":draft.is_dirty(&baseline)}));
}
