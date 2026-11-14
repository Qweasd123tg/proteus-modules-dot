#![allow(dead_code)]
mod settings { pub mod draft; pub mod addons; pub mod mcp; }
use std::{fs,path::PathBuf};
use settings::{draft::Draft,mcp::{McpText,mcp_problems,mcp_text}};
use serde_json::json;
use proteus_contracts::app_protocol::config_builder::ConfigBuilderSnapshot;
fn main(){
 let args:Vec<_>=std::env::args().collect();let mode=&args[1];let root=PathBuf::from(&args[2]);
 let snapshot:ConfigBuilderSnapshot=serde_json::from_slice(&fs::read(root.join("snapshot.json")).unwrap()).unwrap();
 let baseline=Draft::from_snapshot(&snapshot); let mut draft=baseline.clone();
 let field=if mode=="env_append" {McpText::Env} else {McpText::Args};
 let original_text=mcp_text(&baseline.addons.mcp_servers[0],field);
 let edited_text=if mode=="env_append" {format!("{}\nEXTRA=new",original_text)} else {format!("{}\n--tag\nnew",original_text)};
 if mode=="api_control" { draft.edit_mcp(0, |server| server.args.extend(["--tag".to_string(),"new".to_string()])); } else { draft.set_mcp_text(0,field,&edited_text).unwrap(); }
 assert!(mcp_problems(&draft,None).is_empty());
 let mut roundtrip=baseline.clone();roundtrip.set_mcp_text(0,field,&original_text).unwrap();
 let mut unrelated=baseline.clone(); unrelated.set_mcp_text(0,McpText::TimeoutMs,"2500").unwrap();
 assert_eq!(baseline.addons.mcp_servers[0].args,unrelated.addons.mcp_servers[0].args);
 assert_eq!(baseline.addons.mcp_servers[0].environment.env,unrelated.addons.mcp_servers[0].environment.env);
 println!("{}",json!({"request":draft.changes(&baseline),"before":baseline.addons.mcp_servers[0],"after":draft.addons.mcp_servers[0],"exact_text_roundtrip":roundtrip.addons.mcp_servers[0],"same_text_is_dirty":roundtrip.is_dirty(&baseline),"field_text_before":original_text,"field_text_after":edited_text,"final_validation_errors":mcp_problems(&draft,None).len(),"unrelated_edit_preserves_inputs":true}));
}
