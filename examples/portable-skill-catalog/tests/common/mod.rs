#![allow(dead_code)]
use proteus_example_portable_skill_catalog::config::{Config, Root};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicUsize, Ordering},
};
static SEQUENCE: AtomicUsize = AtomicUsize::new(0);

pub struct Fixture {
    pub path: PathBuf,
}
impl Fixture {
    pub fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "proteus-authored-portable-skills-{}-{}",
            std::process::id(),
            SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).expect("create new owned fixture directory");
        Self { path }
    }
    pub fn config(&self) -> Config {
        Config {
            roots: vec![Root {
                id: "project-agents".into(),
                path: self.path.clone(),
            }],
            disabled: Default::default(),
            strict: false,
            max_entries: 32,
            max_skills: 16,
            max_total_bytes: 1_048_576,
            max_context_bytes: 65_536,
        }
    }
    pub fn skill(&self, name: &str, body: &str) -> PathBuf {
        self.raw(
            name,
            &format!("---\nname: {name}\ndescription: Explain authored fixture.\n---\n{body}"),
        )
    }
    pub fn raw(&self, name: &str, text: &str) -> PathBuf {
        write(&self.path, name, text)
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
}
pub fn write(root: &Path, name: &str, text: &str) -> PathBuf {
    let directory = root.join(name);
    fs::create_dir_all(&directory).unwrap();
    let path = directory.join("SKILL.md");
    fs::write(&path, text).unwrap();
    path
}
