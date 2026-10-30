use std::collections::BTreeSet;

use anyhow::{Result, ensure};
use proteus_module_sdk::contracts::domain::{ConfigField, ConfigValueSchema, ModuleConfigSchema};
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    /// Exact explicit allowlist; no polling tools are silently opted in.
    pub observed_tools: BTreeSet<String>,
    #[serde(default = "default_threshold")]
    pub threshold: usize,
    #[serde(default = "default_max_scopes")]
    pub max_scopes: usize,
    #[serde(default = "default_max_observation_bytes")]
    pub max_observation_bytes: usize,
    #[serde(default = "default_idle_ttl_seconds")]
    pub idle_ttl_seconds: u64,
}

fn default_threshold() -> usize {
    3
}
fn default_max_scopes() -> usize {
    32
}
fn default_max_observation_bytes() -> usize {
    32768
}
fn default_idle_ttl_seconds() -> u64 {
    900
}

impl Config {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            (1..=64).contains(&self.observed_tools.len()),
            "observed_tools requires 1..=64 names"
        );
        for name in &self.observed_tools {
            ensure!(
                !name.is_empty()
                    && name.len() <= 128
                    && name
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b)),
                "invalid observed tool name"
            );
        }
        ensure!(
            (2..=16).contains(&self.threshold),
            "threshold must be 2..=16"
        );
        ensure!(
            (1..=128).contains(&self.max_scopes),
            "max_scopes must be 1..=128"
        );
        ensure!(
            (256..=262144).contains(&self.max_observation_bytes),
            "max_observation_bytes must be 256..=262144"
        );
        ensure!(
            self.max_scopes * self.max_observation_bytes <= 8 * 1024 * 1024,
            "retained signature budget exceeds 8 MiB"
        );
        ensure!(
            (1..=86400).contains(&self.idle_ttl_seconds),
            "idle_ttl_seconds must be 1..=86400"
        );
        Ok(())
    }

    pub fn schema() -> ModuleConfigSchema {
        let integer = |min, max| ConfigValueSchema::Integer {
            minimum: Some(min),
            maximum: Some(max),
        };
        ModuleConfigSchema { fields: vec![
            ConfigField::new("observed_tools", "Наблюдаемые инструменты", "1–64 точных имени. Не добавляйте status/wait/poll без осознанного выбора.", ConfigValueSchema::strings()).required(),
            ConfigField::new("threshold", "Порог повторов", "Последовательные одинаковые видимые результаты одного вызова; только advisory.", integer(2, 16)).with_default(3),
            ConfigField::new("max_scopes", "Области наблюдения", "LRU: при вытеснении забываются наблюдения, не останавливается работа.", integer(1, 128)).with_default(32).advanced(),
            ConfigField::new("max_observation_bytes", "Байты сигнатуры", "Превышение пропускается и разрывает серию. Произведение с max_scopes не более 8 MiB.", integer(256, 262144)).with_default(32768).advanced().unit("bytes"),
            ConfigField::new("idle_ttl_seconds", "Время простоя", "Удаление при следующем событии, без фонового потока.", integer(1, 86400)).with_default(900).advanced().unit("seconds"),
        ] }
    }
}
