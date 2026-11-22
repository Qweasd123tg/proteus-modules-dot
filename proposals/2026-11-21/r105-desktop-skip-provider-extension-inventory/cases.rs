use crate::{
    catalog::{
        self, Installed, Source, Target, connections, inventory::Inventory, open::OFFICIAL,
        schema::Kind,
    },
    meter,
};
use proteus_contracts::app_protocol::config_builder::ConfigBuilderSnapshot;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

fn root() -> PathBuf {
    std::env::var_os("R105_FIXTURE").unwrap().into()
}
fn bundle() -> PathBuf {
    std::env::var_os("PROTEUS_EXTENSIONS_DIR").unwrap().into()
}

fn stable(s: &str) -> String {
    s.replace(&*root().display().to_string(), "<fixture>")
        .replace(&*bundle().display().to_string(), "<bundle>")
}

fn package(p: &catalog::inventory::Package) -> Value {
    json!([
        p.version,
        stable(&p.path.display().to_string()),
        p.problem.as_ref().map(|s| stable(s))
    ])
}

fn inventory_snapshot(inventory: &Inventory) -> Value {
    let extensions: Vec<_> = inventory
        .extension_rows()
        .map(|(id, p)| json!([id, package(p)]))
        .collect();
    let modules: Vec<_> = inventory
        .module_packages()
        .map(|(id, p)| json!([id, package(p)]))
        .collect();
    json!({"extensions":extensions,"modules":modules})
}

fn receipt(path: &Path, id: &str) -> Installed {
    Installed {
        source: Source {
            url: "https://example.invalid/fixture".into(),
            branch: None,
        },
        entry: id.into(),
        version: "arbitrary-receipt-marker".into(),
        kind: Kind::ProcessModule,
        profile: Some("nonexistent-fixture-profile".into()),
        target: Target::Component {
            path: path.into(),
            command: vec!["ignored-receipt-command".into()],
            exports: BTreeMap::new(),
            icon: Some("ignored-receipt-icon".into()),
        },
    }
}

fn describe(d: &connections::Discovery) -> Value {
    let choices: Vec<_> = d
        .choices
        .iter()
        .map(|c| {
            let template = &c.template;
            let request = c
                .request(&template.module_id, &ConfigBuilderSnapshot::default())
                .unwrap();
            let normalized_command: Vec<_> = c.command.iter().map(|s| stable(s)).collect();
            let expected_key = catalog::key(&format!("{:?}\n{}", c.command, template.id));
            assert_eq!(c.key(), expected_key);
            json!({
                "key": c.key(),
                "package": c.package,
                "command": normalized_command,
                "icon": c.icon.as_ref().map(|s|stable(s)),
                "named": c.named,
                "id": template.id,
                "title": template.title,
                "description": template.description,
                "module_id": template.module_id,
                "module_config": template.module_config,
                "env_allowlist": template.env_allowlist,
                "auth":template.auth.as_ref().map(|a|json!([a.command,a.credential_file_key])),
                "request": stable(&serde_json::to_string(&request).unwrap())
            })
        })
        .collect();
    json!([
        choices,
        d.problems.iter().map(|s| stable(s)).collect::<Vec<_>>()
    ])
}

#[test]
fn public_provider_discovery_and_catalog_have_separate_work() {
    eprintln!("ARM {}", env!("R105_PROVIDER_ARM"));
    let root = root();
    let receipts = [
        receipt(&root.join("ready"), "alpha-first"),
        receipt(&root.join("receipt"), "explicit"),
    ];
    let (d, provider) = meter::record(|| connections::discover(&receipts));
    let (full, catalog) = meter::record(Inventory::local);
    let titles: Vec<_> = d
        .choices
        .iter()
        .map(|c| c.template.title.as_str())
        .collect();
    assert_eq!(titles, ["A shared", "B fixed", "C receipted"]);
    assert_eq!(d.choices[1].package, "manifest-id");
    assert!(!d.choices[1].named);
    assert_eq!(
        d.choices[0].template.auth.as_ref().unwrap().command,
        ["metadata-only", "status"]
    );
    assert!(d.choices.iter().all(|c| c.command[1] == "--inert"));
    let errors: Vec<_> = d
        .problems
        .iter()
        .map(|p| p.split_once(':').unwrap().0)
        .collect();
    assert_eq!(
        errors,
        [
            "malformed",
            "missing-program",
            "not-directory",
            "outside-relative",
            "oversize",
            "tampered"
        ]
    );
    assert_eq!(full.extension_rows().count(), 14);
    assert!(
        full.module_packages()
            .find(|(id, _)| *id == "mismatched")
            .unwrap()
            .1
            .problem
            .is_some()
    );
    assert_eq!(catalog[0..5], [2, 14, 1, 1, 1]);
    eprintln!("TRACE provider {}", describe(&d));
    eprintln!("TRACE catalog {}", inventory_snapshot(&full));
    meter::print("provider", provider);
    meter::print("catalog", catalog);

    let user = root.join("xdg/dev.proteus.native/extensions/git");
    fs::create_dir_all(&user).unwrap();
    fs::write(user.join("extension.json"), b"{inert broken override").unwrap();
    let (new, new_work) = meter::record(|| connections::discover(&receipts));
    let (new_catalog, new_catalog_work) = meter::record(Inventory::local);
    let broken = new_catalog
        .find(&OFFICIAL[1].source(), Kind::ClientExtension, "git")
        .unwrap();
    assert_eq!(broken.path, user);
    assert!(broken.problem.is_some());
    assert_eq!(describe(&new), describe(&d));
    assert_eq!(&provider[8..], &new_work[8..]);
    eprintln!(
        "TRACE overridden-catalog {}",
        inventory_snapshot(&new_catalog)
    );
    meter::print("provider-with-broken-extension", new_work);
    meter::print("catalog-with-broken-extension", new_catalog_work);
    fs::remove_dir_all(root.join("xdg")).unwrap();
}

#[test]
fn absent_backend_keeps_explicit_component_receipt() {
    assert!(!Path::new(&std::env::var_os("PROTEUS_BIN").unwrap()).exists());
    let root = root();
    let (only, work) =
        meter::record(|| connections::discover(&[receipt(&root.join("receipt"), "explicit")]));
    assert_eq!(only.choices.len(), 1);
    assert_eq!(only.choices[0].package, "explicit");
    assert!(only.problems.is_empty());
    eprintln!("TRACE absent-backend {}", describe(&only));
    meter::print("absent-backend", work);
}
