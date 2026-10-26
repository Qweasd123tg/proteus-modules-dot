//! Real pinned Core assembly/adapters plus explicitly authored offline fixtures.
//! Does not run an upstream test suite, reference pack, external model, or user hook.
mod fixture;
mod scenarios;
mod support;

use anyhow::{Result, ensure};
use serde_json::json;

fn main() -> Result<()> {
    if std::env::args().nth(1).as_deref() == Some("--fixture") {
        return proteus_module_sdk::run(fixture::load);
    }
    ensure!(
        std::env::args().len() == 1,
        "no positional arguments supported"
    );
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()?;
    let report = runtime.block_on(scenarios::run())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "schema_version":1,
            "core_commit":"3f36a003b4f3fde2242fc80f7aedac00dd127d1d",
            "scope":"real Core AppConfig/assembly/BoundTools/hook/context adapters; model-free component integration",
            "not_claimed":["complete agent turn", "official reference pack pairing", "real verifier evidence", "journal/replay", "OS sandbox", "external model quality"],
            "checks":report
        }))?
    );
    Ok(())
}
