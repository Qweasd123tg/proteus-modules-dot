use std::{fs,path::{Path,PathBuf}};
use serde_json::json;
use catalog_mcp_toggle_probe::{catalog::{self,install,Locations,Installed,Source,schema::{Catalog,Entry}},settings::Draft};
use proteus_contracts::app_protocol::config_builder::ConfigBuilderSnapshot;
fn prepared(root:&Path,enabled:bool,version:&str,old:Option<&Installed>)->Installed {
 let dir=root.join("catalog/demo");fs::create_dir_all(&dir).unwrap();
 fs::write(dir.join("server.json"),json!({"name":"demo","command":"python3","args":["-B",root.join("mcp.py")],"enabled":enabled}).to_string()).unwrap();
 let entry:Entry=serde_json::from_value(json!({"id":"demo","kind":"mcp_server","title":"Demo","category":"mcp","version":version,"path":"demo"})).unwrap();
 let cat=Catalog{root:root.join("catalog"),revision:None,title:"Fixture".into(),categories:vec![],entries:vec![entry.clone()],problems:vec![]};
 let loc=Locations{cache:root.join("cache"),extensions:root.join("extensions"),plugins:root.join("plugins"),skills:root.join("skills"),modules:root.join("modules")};
 install::prepare(&loc,&Source{url:"https://example.invalid/fixture/mcp".into(),branch:None},&cat,&entry,old,&root.join("profile.toml"),&[]).unwrap()
}
fn main(){
 let mut args=std::env::args().skip(1);let mode=args.next().unwrap();let root=PathBuf::from(args.next().unwrap());
 let snapshot:ConfigBuilderSnapshot=serde_json::from_slice(&fs::read(root.join("snapshot.json")).unwrap()).unwrap();
 let baseline=Draft::from_snapshot(&snapshot);
 let mut draft=baseline.clone();
 match mode.as_str(){
  "prepare"=>{let v1=prepared(&root,false,"1",None);install::connect(&mut draft,&v1,None).unwrap();fs::write(root.join("receipt.json"),serde_json::to_vec_pretty(&v1).unwrap()).unwrap();println!("{}",serde_json::to_string(&draft.changes(&baseline)).unwrap());},
  "toggle"=>{assert!(!draft.mcp_enabled("demo"));draft.set_mcp("demo",true);assert!(draft.mcp_enabled("demo"));println!("{}",serde_json::to_string(&draft.changes(&baseline)).unwrap());},
  "check"=>{
   let receipt:Installed=serde_json::from_slice(&fs::read(root.join("receipt.json")).unwrap()).unwrap();
   assert!(draft.configured_mcp("demo").unwrap().enabled);
   assert!(install::connected(&receipt,&draft));
   let v2=prepared(&root,false,"2",Some(&receipt));
   let update=install::connect(&mut draft,&v2,Some(&receipt)).unwrap_err().to_string();
   assert_eq!(draft,baseline);
   let remove=install::disconnect(&mut draft,&receipt).unwrap_err().to_string();assert_eq!(draft,baseline);
   // Toggling back off does not restore enabled=false: UI tracks false in disabled list.
   let mut toggled_back=baseline.clone();toggled_back.set_mcp("demo",false);
   let still_true=toggled_back.configured_mcp("demo").unwrap().enabled;assert!(still_true);
   let retry=install::connect(&mut toggled_back,&v2,Some(&receipt)).unwrap_err().to_string();
   // Control: disabled-by-default and untouched succeeds.
   let mut untouched=Draft::default();install::connect(&mut untouched,&receipt,None).unwrap();install::connect(&mut untouched,&v2,Some(&receipt)).unwrap();assert!(!untouched.mcp_enabled("demo"));
   // Control: initially enabled, then normal UI off/on retains update support.
   let active=prepared(&root,true,"1",None);let active2=prepared(&root,true,"2",Some(&active));
   let mut normal=Draft::default();install::connect(&mut normal,&active,None).unwrap();normal.set_mcp("demo",false);install::connect(&mut normal,&active2,Some(&active)).unwrap();assert!(!normal.mcp_enabled("demo"));normal.set_mcp("demo",true);install::connect(&mut normal,&active2,Some(&active2)).unwrap();assert!(normal.mcp_enabled("demo"));
   // Control: an actual manual command edit remains protected.
   let mut edited=Draft::default();install::connect(&mut edited,&active,None).unwrap();edited.addons.mcp_servers[0].command="changed".into();assert!(install::connect(&mut edited,&active2,Some(&active)).is_err());
   println!("{}",json!({"update_error":update,"remove_error":remove,"toggle_back_off_retry_error":retry,"after_toggle_back_off_server_enabled":still_true,"connected_status_despite_update_failure":true,"failed_update_preserves_draft":true,"untouched_disabled_control":"pass","initial_enabled_off_on_control":"pass","manual_command_edit_guard_control":"pass"}));
  },_=>panic!("mode")
 }
}
