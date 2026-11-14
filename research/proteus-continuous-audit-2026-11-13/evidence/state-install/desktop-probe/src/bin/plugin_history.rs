#![allow(dead_code,unused_imports)]
use std::{path::PathBuf,fs};
mod settings { pub use desktop_state_history_probe::settings::draft::Draft; }
#[path="/workspace/shared/state-install-trace/src/packages.rs"] mod packages;
// Unused extension/source-build edges are compile-only stubs. Plugin folder
// prepare, connect, binding, receipt replacement and Draft are original code.
mod declarative { pub mod manifest {
    pub struct Manifest {pub id:String}
    pub fn parse(_: &str)->anyhow::Result<Manifest>{anyhow::bail!("extension edge unused")}
    pub fn load(_: &std::path::Path)->anyhow::Result<Manifest>{anyhow::bail!("extension edge unused")}
} }
mod catalog {
    include!("../catalog_types.rs");
    #[path="/workspace/shared/state-install-trace/src/catalog/schema.rs"] pub mod schema;
    #[path="/workspace/shared/state-install-trace/src/catalog/skills.rs"] pub mod skills;
    #[path="/workspace/shared/state-install-trace/src/catalog/open.rs"] pub mod open;
    #[path="/workspace/shared/state-install-trace-evidence/desktop-probe/src/install_plugin_probe.rs"] pub mod install;
    pub mod build {
        pub fn prepare(_: &super::Locations, _: &super::Source, _: &super::schema::Catalog,
                       _: &super::schema::Entry)->anyhow::Result<crate::packages::Contents> {
            anyhow::bail!("source-build edge unused")
        }
    }
}
fn main() {
    let root=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("plugin-history-fixture");
    fs::create_dir_all(&root).unwrap();
    let root=root.join(uuid::Uuid::new_v4().to_string());
    let source_root=root.join("source");
    fs::create_dir_all(source_root.join("demo")).unwrap();
    let locations=catalog::Locations {cache:root.join("cache"),extensions:root.join("extensions"),
        plugins:root.join("plugins"),skills:root.join("skills"),modules:root.join("modules")};
    let source=catalog::Source {url:"https://example.invalid/plugins".into(),branch:None};
    let profile=root.join("profile.toml");
    let mut draft=settings::Draft::default();
    let mut prefs=catalog::Preferences::default();
    let make=|version:&str, previous:Option<&catalog::Installed>| {
        fs::write(source_root.join("demo/plugin.json"),serde_json::json!({
            "$schema":"https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name":"demo","version":version
        }).to_string()).unwrap();
        let entry:catalog::schema::Entry=serde_json::from_value(serde_json::json!({
            "id":"demo","kind":"agent_plugin","title":"Demo","category":"plugins",
            "version":version,"path":"demo"
        })).unwrap();
        let catalog=catalog::schema::Catalog { root:source_root.clone(),revision:None,
            title:"Test".into(),categories:vec![],entries:vec![entry.clone()],problems:vec![]};
        catalog::install::prepare(&locations,&source,&catalog,&entry,previous,&profile,&[]).unwrap()
    };
    let v1=make("1",None);
    catalog::install::connect(&mut draft,&v1,None).unwrap();
    let prior_state=proteus_contracts::app_protocol::config_builder::ConfigBuilderState {
        addon_settings:draft.addons.clone(), ..Default::default()
    };
    prefs.remember(v1.clone());
    let v2=make("2",prefs.installed.first());
    catalog::install::connect(&mut draft,&v2,prefs.installed.first()).unwrap();
    prefs.remember(v2.clone());
    assert_eq!(draft.addons.addons.plugins.len(),1);
    // History restore affects profile only, not catalog Preferences receipts.
    let snapshot=proteus_contracts::app_protocol::config_builder::ConfigBuilderSnapshot {
        addon_settings:draft.addons.clone(), ..Default::default()
    };
    draft=settings::Draft::from_revision(&snapshot,&prior_state);
    assert!(!catalog::install::connected(prefs.installed.first().unwrap(),&draft));
    let v3=make("3",prefs.installed.first());
    catalog::install::connect(&mut draft,&v3,prefs.installed.first()).unwrap();
    assert_eq!(draft.addons.addons.plugins.len(),2);
    let names:Vec<_>=draft.addons.addons.plugins.iter().map(|p| {
        serde_json::from_str::<serde_json::Value>(&fs::read_to_string(p.path.join("plugin.json")).unwrap()).unwrap()["name"].as_str().unwrap().to_owned()
    }).collect();
    assert_eq!(names,vec!["demo","demo"]);
    fs::write(root.join("post-connect-addons.json"),serde_json::to_vec_pretty(&draft.addons).unwrap()).unwrap();
    println!("fixture={}; after catalog v1→v2, history→v1, catalog→v3: bindings={}, names={:?}, stable keys={:?}",root.display(),draft.addons.addons.plugins.len(),names,draft.addons.addons.plugins.iter().map(|p|p.data_key.clone()).collect::<Vec<_>>());
    println!("payload={}",serde_json::to_string(&draft.addons).unwrap());
}
