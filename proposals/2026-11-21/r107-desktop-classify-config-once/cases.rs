use crate::{catalog, meter};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
};

fn put(root: &Path, relative: &str, bytes: impl AsRef<[u8]>) -> PathBuf {
    let p = root.join(relative);
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(&p, bytes).unwrap();
    p
}

struct Fixture(PathBuf);
impl Fixture {
    fn new(label: &str) -> Self {
        let p = PathBuf::from("build/focused").join(label);
        fs::create_dir_all(&p).unwrap();
        Self(p)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

fn snapshot(catalog: &catalog::Catalog, root: &Path) -> Value {
    let result: Vec<_> = catalog
        .files
        .iter()
        .map(|f| {
            json!([
                f.path.strip_prefix(root).unwrap(),
                f.relative,
                f.name,
                f.title,
                f.display_name(),
                f.current,
                f.entrypoint,
                f.duplicate_name
            ])
        })
        .collect();
    json!({"rows":result,"problem":catalog.problem.as_ref().map(|p|p.replace(&*root.display().to_string(),"<root>"))})
}

fn inspect(label: &str, root: &Path, current: Option<PathBuf>) -> catalog::Catalog {
    let (rows, work) = meter::record(|| catalog::discover(Some(root.to_owned()), current));
    eprintln!("TRACE {label} {}", snapshot(&rows, root));
    eprintln!("WORK {label}: {work:?}");
    rows
}

#[test]
fn actual_portable_profile_corpus_keeps_labels_and_current_row() {
    eprintln!("ARM {}", env!("R107_CONFIG_ARM"));
    let root = PathBuf::from(std::env::var_os("R107_PROFILES").unwrap());
    let rows = inspect(
        "portable",
        &root,
        Some(root.join("configs/codex-task.config.toml")),
    );
    assert!(rows.problem.is_none());
    assert_eq!(rows.files.len(), 8);
    let found: Vec<_> = rows
        .files
        .iter()
        .map(|f| (f.display_name(), f.entrypoint))
        .collect();
    assert_eq!(
        found,
        [
            ("Codex", true),
            ("codex-coder.config.toml", false),
            ("codex-explore.config.toml", false),
            ("codex-subscription.config.toml", false),
            ("codex-task.config.toml", false),
            ("OpenCode", true),
            ("Pi", true),
            ("Proteus", true)
        ]
    );
    let current: Vec<_> = rows
        .files
        .iter()
        .filter(|r| r.current)
        .map(|r| r.name.as_str())
        .collect();
    assert_eq!(current, ["codex-task.config.toml"]);
}

#[test]
fn lexical_winners_current_and_nonregular_classification() {
    use std::os::unix::{ffi::OsStringExt, fs::symlink};
    let f = Fixture::new("types");
    let root = f.0.join("setup");
    let target = put(
        &f.0,
        "outside/target.txt",
        r#"{"profile":{"title":"  Same  ","entrypoint":false}}"#,
    )
    .canonicalize()
    .unwrap();
    let aliased = put(
        &root,
        ".outside/symlinked-dir/kept.toml",
        "[profile]\ntitle = 'Name through directory'",
    );
    symlink(".outside/symlinked-dir", root.join("configs")).unwrap();
    put(&root, "clones/configs/b.toml", "[profile]\ntitle = 'Same'");
    symlink(&target, root.join("a-earlier.json")).unwrap();
    symlink(&target, root.join("z-later.json")).unwrap();
    symlink("absent", root.join("missing.toml")).unwrap();
    symlink("self.json", root.join("self.json")).unwrap();
    symlink("..", root.join("clones/cycle")).unwrap();
    fs::create_dir_all(root.join("configs/not-a-file.toml/configs")).unwrap();
    put(
        &root,
        "configs/not-a-file.toml/configs/ignored.toml",
        "should not appear",
    );
    put(
        &root,
        "configs/nonprofile.example.toml",
        "should not appear",
    );
    put(&root, "configs/malformed.json", "{{not-json");
    put(
        &root,
        "clones/secret.toml",
        "ignored outside the profiles parent",
    );
    let path = root
        .join("configs")
        .join(std::ffi::OsString::from_vec(b"non-utf8-\xff.toml".to_vec()));
    fs::write(path, b"ignored").unwrap();
    // A character-device target is nonregular even when its alias looks
    // like JSON. Discovery must never open it for profile labels.
    symlink("/dev/null", root.join("configs/nonregular.json")).unwrap();
    let rows = inspect("types", &root, Some(target));
    assert!(rows.problem.is_none());
    let ordered: Vec<_> = rows.files.iter().map(|f| f.relative.as_str()).collect();
    assert_eq!(
        ordered,
        [
            "configs/malformed.json",
            "configs/kept.toml",
            "a-earlier.json",
            "clones/configs/b.toml"
        ]
    );
    let win = &rows.files[2];
    assert_eq!(win.path, root.join("a-earlier.json"));
    assert_eq!(win.title.as_deref(), Some("Same"));
    assert!(win.current && win.duplicate_name && !win.entrypoint);
    assert!(rows.files[3].duplicate_name);
    assert_eq!(
        rows.files[1].path.canonicalize().unwrap(),
        aliased.canonicalize().unwrap()
    );
}

#[test]
fn limits_and_non_directory_keep_their_existing_diagnostics() {
    let f = Fixture::new("limits");
    let deep = f.0.join("deep");
    put(
        &deep,
        "one/two/three/four/five/six/configs/unreachable.toml",
        "",
    );
    let rows = inspect("depth", &deep, None);
    assert!(rows.files.is_empty());
    assert!(
        rows.problem
            .unwrap()
            .starts_with("Глубина списка ограничена")
    );

    let dirs = f.0.join("directories");
    for i in 0..=256 {
        fs::create_dir_all(dirs.join(format!("d{i:04}"))).unwrap();
    }
    let rows = inspect("directories", &dirs, None);
    assert!(rows.files.is_empty() && rows.problem.unwrap().starts_with("Список ограничен"));

    let crowded = f.0.join("entries");
    fs::create_dir_all(&crowded).unwrap();
    for i in 0..8193 {
        fs::File::create(crowded.join(format!(".ignored-{i:05}"))).unwrap();
    }
    let rows = inspect("entries", &crowded, None);
    assert!(rows.files.is_empty() && rows.problem.unwrap().starts_with("Список ограничен"));

    let bytes = f.0.join("bytes");
    // Exact 32 * 256 KiB, then two fallback rows that remain visible.
    let raw = " ".repeat(256 * 1024);
    for i in 0..32 {
        put(&bytes, &format!("configs/{i:03}.toml"), &raw);
    }
    put(
        &bytes,
        "configs/032.toml",
        "[profile]\ntitle='Beyond budget'",
    );
    put(
        &bytes,
        "configs/033.toml",
        "[profile]\ntitle='Also beyond budget'",
    );
    let rows = inspect("label-byte-sum", &bytes, None);
    assert_eq!(rows.files.len(), 34);
    assert!(rows.files.iter().all(|r| r.title.is_none()));
    assert!(
        rows.problem
            .unwrap()
            .starts_with("Часть подписей не прочитана")
    );

    let file = put(&f.0, "root-file", "inert");
    let rows = inspect("non-directory-root", &file, None);
    assert!(rows.files.is_empty());
    assert!(rows.problem.unwrap().contains("Не удалось прочитать"));
}
