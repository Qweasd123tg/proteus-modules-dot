use crate::{
    catalog::{Source, inventory::Inventory, open::OFFICIAL, schema::Kind},
    declarative::manifest,
    meter,
};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
};

fn package(p: &crate::catalog::inventory::Package, root: &Path) -> Value {
    let path = p.path.strip_prefix(root).unwrap().to_string_lossy();
    let error = p
        .problem
        .as_ref()
        .map(|s| s.replace(&*root.display().to_string(), "<root>"));
    json!([p.version, path, error])
}

fn inventory_snapshot(inventory: &Inventory, extensions: &Path, modules: &Path) -> Value {
    let extensions: Vec<_> = inventory
        .extension_rows()
        .map(|(id, p)| json!([id, package(p, extensions)]))
        .collect();
    let modules: Vec<_> = inventory
        .module_packages()
        .map(|(id, p)| json!([id, package(p, modules)]))
        .collect();
    json!({"extensions":extensions,"modules":modules})
}

#[test]
fn ordinary_sealed_package_inventory_and_runtime_agree() {
    eprintln!("ARM {}", env!("R103_INVENTORY_ARM"));
    let root = PathBuf::from(std::env::var_os("R103_PACKAGES").unwrap());
    let (inventory, work) = meter::record(|| Inventory::read(None, &root, None));
    let ((installed, problems), runtime) =
        meter::record(|| manifest::discover_sources(&root, None));
    assert!(problems.is_empty(), "{problems:?}");
    assert_eq!(inventory.extension_rows().count(), 14);
    assert_eq!(installed.len(), 14);
    for entry in &installed {
        let found = inventory
            .find(
                &OFFICIAL[1].source(),
                Kind::ClientExtension,
                &entry.manifest.id,
            )
            .unwrap();
        assert_eq!(found.path, entry.dir);
        assert_eq!(found.version, None);
        assert_eq!(found.problem, None);
    }
    assert_eq!(&work[..5], &runtime[..5]);
    assert_eq!(runtime[5..], [14, 41, 152]);
    eprintln!(
        "TRACE ordinary-inventory {}",
        inventory_snapshot(&inventory, &root, &root)
    );
    eprintln!(
        "TRACE ordinary-runtime {}",
        json!(
            installed
                .iter()
                .map(|entry| (&entry.manifest.id, entry.revision))
                .collect::<Vec<_>>()
        )
    );
    meter::print("ordinary-inventory", work);
    meter::print("ordinary-runtime", runtime);
}

fn write(dir: &Path, name: &str, bytes: impl AsRef<[u8]>) {
    fs::create_dir_all(dir).unwrap();
    fs::write(dir.join(name), bytes).unwrap();
}

fn declaration(id: &str) -> Value {
    json!({"protocol":4,"id":id,"title":format!("Fixture {id}"),"command":["never-executed"],"surfaces":{"page":{}}})
}

fn extension(root: &Path, id: &str) -> PathBuf {
    let path = root.join(id);
    write(&path, manifest::MANIFEST, declaration(id).to_string());
    path
}

fn broken(root: &Path, id: &str) -> PathBuf {
    let path = root.join(id);
    write(&path, manifest::MANIFEST, "{broken");
    path
}

fn report(root: &Path, problems: Vec<manifest::Problem>) -> Vec<Value> {
    problems
        .into_iter()
        .map(|p| {
            json!([
                p.dir.strip_prefix(root).unwrap().to_string_lossy(),
                p.error.replace(&root.display().to_string(), "<root>"),
            ])
        })
        .collect()
}

#[test]
fn exact_catalog_validation_and_bundle_user_precedence() {
    use std::os::unix::{ffi::OsStringExt, fs::symlink};
    let root = PathBuf::from("build/r103-synthetic");
    fs::create_dir_all(&root).unwrap();
    struct Cleanup(PathBuf);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }
    let _cleanup = Cleanup(root.clone());
    let bundle = root.join("bundle");
    let user = root.join("user");
    let external = root.join("inert");
    extension(&bundle, "healthy");
    extension(&bundle, "replace");
    extension(&user, "replace");
    extension(&bundle, "masked-file");
    write(&user, "masked-file", "not a package");
    extension(&bundle, "mask-link-file");
    symlink("masked-file", user.join("mask-link-file")).unwrap();
    extension(&bundle, "dangling");
    symlink("missing", user.join("dangling")).unwrap();
    extension(&bundle, "broken-user");
    broken(&user, "broken-user");
    broken(&bundle, "broken-base");
    extension(&user, "broken-base");
    broken(&bundle, "both-broken");
    broken(&user, "both-broken");
    broken(&bundle, "broken-shadow");
    write(&user, "broken-shadow", "still show bundled diagnostic");
    broken(&bundle, ".hidden");
    broken(&bundle, &"a".repeat(50));
    let invalid_name = std::ffi::OsString::from_vec(b"bad-\xff".to_vec());
    write(
        &bundle.join(&invalid_name),
        manifest::MANIFEST,
        declaration("otherwise-ok").to_string(),
    );
    let aliased = external.join("real-alias");
    write(
        &aliased,
        manifest::MANIFEST,
        declaration("alias").to_string(),
    );
    symlink("../inert/real-alias", user.join("alias")).unwrap();
    let instruction = |id: &str| {
        let mut v = declaration(id);
        v["required_features"] = json!(["manifest.agent_instructions.v1"]);
        v["agent_instructions"] = json!([{"skill":"fixture/read","path":"skills/read"}]);
        v
    };
    write(
        &user.join("owned-skill"),
        manifest::MANIFEST,
        instruction("owned-skill").to_string(),
    );
    write(&user.join("owned-skill/skills/read"), "SKILL.md", "inert");
    write(
        &user.join("bad-skill"),
        manifest::MANIFEST,
        instruction("bad-skill").to_string(),
    );
    fs::create_dir_all(user.join("bad-skill/skills")).unwrap();
    write(&external, "SKILL.md", "inert external");
    symlink("../../../inert", user.join("bad-skill/skills/read")).unwrap();

    let modules = root.join("ready");
    write(&modules.join("bin"), "proteus", "never run");
    write(&modules.join("bin"), "probe", "not executable");
    for (id, command) in [
        ("good", Some("bin/probe")),
        ("missing", Some("bin/missing")),
        ("outside", Some("../probe")),
        ("invalid", None),
    ] {
        write(
            &modules.join("share/modules").join(id),
            "module.json",
            command.map_or_else(
                || "{bad json".into(),
                |command| json!({"id":id,"version":"fixture","command":[command]}).to_string(),
            ),
        );
    }
    let (inventory, work) =
        meter::record(|| Inventory::read(Some(&modules.join("bin/proteus")), &bundle, Some(&user)));
    let ((installed, problems), runtime) =
        meter::record(|| manifest::discover_sources(&bundle, Some(&user)));
    assert_eq!(&work[..5], &runtime[..5]);
    let present: Vec<_> = installed.iter().map(|e| e.manifest.id.as_str()).collect();
    assert_eq!(
        present,
        [
            "dangling",
            "healthy",
            "alias",
            "broken-base",
            "owned-skill",
            "replace"
        ]
    );
    let inspected = |id: &str| inventory.find(&OFFICIAL[1].source(), Kind::ClientExtension, id);
    for claimed in ["masked-file", "mask-link-file", ".hidden", "bad-�"] {
        assert!(inspected(claimed).is_none());
    }
    for (id, path) in [
        ("broken-user", user.join("broken-user")),
        ("both-broken", user.join("both-broken")),
        ("broken-shadow", bundle.join("broken-shadow")),
        ("bad-skill", user.join("bad-skill")),
        (&"a".repeat(50), bundle.join("a".repeat(50))),
    ] {
        let p = inspected(id).unwrap();
        assert_eq!(p.path, path);
        assert!(p.problem.is_some());
    }
    assert!(inspected("broken-base").unwrap().problem.is_none());
    assert!(inspected("dangling").unwrap().path.starts_with(&bundle));
    assert_eq!(inspected("alias").unwrap().path, user.join("alias"));
    assert!(
        inspected("bad-skill")
            .unwrap()
            .problem
            .as_ref()
            .unwrap()
            .contains("inside the package")
    );
    let broken_id_dirs: Vec<_> = problems
        .iter()
        .map(|p| p.dir.file_name().unwrap().to_string_lossy().into_owned())
        .collect();
    assert!(
        broken_id_dirs
            .windows(2)
            .any(|pair| pair[0] == "both-broken" && pair[1] == "broken-base")
    );
    assert_eq!(
        broken_id_dirs
            .iter()
            .filter(|id| id.as_str() == "both-broken")
            .count(),
        2
    );
    assert!(
        Inventory::read(None, &root.join("absent"), Some(&root.join("also-absent")))
            .extension_rows()
            .next()
            .is_none()
    );
    let absent = Source {
        url: "https://example.invalid/package".into(),
        branch: None,
    };
    assert!(
        inventory
            .find(&absent, Kind::ClientExtension, "healthy")
            .is_none()
    );
    assert!(
        inventory
            .find(&OFFICIAL[0].source(), Kind::ClientExtension, "healthy")
            .is_none()
    );
    assert_eq!(
        inventory
            .find(&OFFICIAL[0].source(), Kind::ProcessModule, "good")
            .unwrap()
            .version
            .as_deref(),
        Some("fixture")
    );
    for id in ["invalid", "missing", "outside"] {
        assert!(
            inventory
                .find(&OFFICIAL[0].source(), Kind::ProcessModule, id)
                .unwrap()
                .problem
                .is_some()
        );
    }
    eprintln!(
        "TRACE synthetic-inventory {}",
        inventory_snapshot(&inventory, &root, &root)
    );
    eprintln!(
        "TRACE synthetic-native {}",
        json!([present, report(&root, problems)])
    );
    meter::print("synthetic-inventory", work);
    meter::print("synthetic-runtime", runtime);

    let revision = || {
        let (rows, _) = manifest::discover_sources(&bundle, Some(&user));
        rows.into_iter()
            .find(|r| r.manifest.id == "healthy")
            .unwrap()
            .revision
    };
    let unchanged = revision();
    write(&bundle.join("healthy"), ".hidden", "ignored");
    write(&bundle.join("healthy/__pycache__"), "cache", "ignored");
    assert_eq!(revision(), unchanged);
    write(&bundle.join("healthy/assets"), "new", "live file");
    assert_ne!(revision(), unchanged);
    let later = Inventory::read(Some(&modules.join("bin/proteus")), &bundle, Some(&user));
    assert_eq!(
        inventory_snapshot(&later, &root, &root),
        inventory_snapshot(&inventory, &root, &root)
    );
    eprintln!("TRACE revision-edits hidden-and-cache-unchanged visible-asset-new inventory-stable");
}
