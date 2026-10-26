//! Operator-side helper: stdin is JSON configuration, not executable code.
//! This prints expectations only. It never changes host policy or configuration.
use anyhow::{Result, ensure};
use proteus_example_json_contracts::{
    JsonContracts,
    config::{Config, MAX_CONFIG_BYTES},
};
use std::io::{self, Read};

fn main() -> Result<()> {
    let mut bytes = Vec::new();
    io::stdin()
        .take((MAX_CONFIG_BYTES + 1) as u64)
        .read_to_end(&mut bytes)?;
    ensure!(
        bytes.len() <= MAX_CONFIG_BYTES,
        "configuration input exceeds byte bound"
    );
    let config: Config = serde_json::from_slice(&bytes)?;
    let module = JsonContracts::new(config)?;
    println!(
        "{}",
        serde_json::to_string_pretty(&serde_json::json!({
            "mode":"strict_json_contracts", "expected":module.expected_policy()
        }))?
    );
    Ok(())
}
