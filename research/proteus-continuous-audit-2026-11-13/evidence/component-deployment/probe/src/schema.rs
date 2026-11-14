use std::path::{Path,Component};
use anyhow::{Result,ensure};
use serde::{Serialize,Deserialize};
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    ProcessModule,
    ClientExtension,
    AgentPlugin,
    Skill,
    McpServer,
}

pub fn slug(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 64
        && !id.starts_with('-')
        && id
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
}

/// Reject absolute paths, parent traversal and repository metadata.
pub fn relative(path: &Path) -> Result<()> {
    ensure!(!path.as_os_str().is_empty(), "Пустой путь");
    ensure!(
        path.components().all(|part| match part {
            Component::Normal(name) => name != ".git",
            Component::CurDir => true,
            _ => false,
        }),
        "Путь должен оставаться внутри каталога: {}",
        path.display()
    );
    Ok(())
}

