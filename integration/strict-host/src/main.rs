//! Authored public-API observer. Reports are captured facts, not a PASS gate;
//! the separate verifier checks the exact scenario and retained journal facts.
mod admission;
mod approval;
mod config;

use anyhow::{Context, Result, ensure};
use proteus_core::core::{AgentRuntime, JournalEntry, ModuleCatalog, SessionStore};
use proteus_example_json_receipt::{ExpectedPolicy, RECEIPT_KEY, verify_receipt};
use proteus_module_sdk::contracts::contracts::CancellationToken;
use proteus_strict_host_fixture::{RELATIVE_PATH, VERIFY_ID};
use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    sync::Arc,
};

const CASES: &[&str] = &[
    "matching",
    "wrong_suite",
    "wrong_config",
    "missing_assertion",
    "omitted",
    "read_denied",
    "approval_denied",
    "default_deny",
];
fn path(arg: &str) -> Result<PathBuf> {
    let path = PathBuf::from(arg);
    ensure!(path.is_absolute(), "paths must be absolute");
    Ok(path)
}
fn write_json(path: &Path, value: &Value) -> Result<()> {
    use std::io::Write;
    let bytes = serde_json::to_vec_pretty(value)?;
    ensure!(bytes.len() <= 8 * 1024 * 1024, "report exceeds 8 MiB");
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(&bytes)?;
    Ok(())
}
#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    ensure!(
        args.len() == 8,
        "usage: host CASE NEW_CASE_DIR OFFICIAL FIXTURE PRODUCER GATE COMPILED_POLICY_JSON"
    );
    let scenario = &args[1];
    ensure!(CASES.contains(&scenario.as_str()), "unknown case");
    let root = path(&args[2])?;
    // Runner creates only the isolated environment parent, never this case root.
    std::fs::create_dir(&root).context("case directory must not exist")?;
    let cwd = root.join("workspace");
    std::fs::create_dir(&cwd)?;
    ensure!(
        cwd.canonicalize()?.as_os_str() == cwd.as_os_str(),
        "workspace spelling must be canonical"
    );
    let binaries = [
        path(&args[3])?,
        path(&args[4])?,
        path(&args[5])?,
        path(&args[6])?,
    ];
    for binary in &binaries {
        ensure!(binary.is_file(), "missing executable {}", binary.display());
    }
    let policy_path = path(&args[7])?;
    let policy_bytes = std::fs::read(&policy_path)?;
    ensure!(policy_bytes.len() < 128 * 1024, "policy input too large");
    let original: Value = serde_json::from_slice(&policy_bytes)?;
    ensure!(
        original["mode"] == "strict_json_contracts",
        "wrong compiled policy mode"
    );
    let expected: ExpectedPolicy = serde_json::from_value(original["expected"].clone())?;
    proteus_example_json_receipt::validate_expected(&expected)?;
    let config = config::make(scenario, &root, &cwd, &binaries, original.clone())?;
    write_json(&root.join("config.json"), &serde_json::to_value(&config)?)?;
    if scenario == "default_deny" {
        let report = admission::run(config, cwd.clone()).await?;
        ensure!(
            !cwd.join(RELATIVE_PATH).exists(),
            "denied write created fixture"
        );
        write_json(
            &root.join("report.json"),
            &json!({"scenario":scenario,"scope":"direct_admission_not_turn","cwd":cwd,"facts":report}),
        )?;
        return Ok(());
    }
    let approvals = Arc::new(approval::ExactApproval::new(
        cwd.clone(),
        scenario == "approval_denied",
    ));
    let gate_policy =
        config.module_config["hook"]["hermes.verify_evidence"]["receipt_policy"].clone();
    let gate_expected: ExpectedPolicy = serde_json::from_value(gate_policy["expected"].clone())?;
    let catalog = ModuleCatalog::from_config(&config)?;
    let config_path = root.join("config.json");
    let runtime = AgentRuntime::builder(config, cwd.clone())
        .with_config_path(Some(&config_path))
        .with_module_catalog(catalog)
        .with_approval(approvals.clone())
        .build_async()
        .await?;
    let token = CancellationToken::new();
    let cancel = token.clone();
    let timer = tokio::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_secs(40)).await;
        cancel.cancel();
    });
    let outcome = runtime
        .run_with_cancellation(
            "Perform the exact authored write and configured verification, then stop.".into(),
            token,
        )
        .await;
    timer.abort();
    let outcome = match outcome {
        Ok(output) => json!({"status":"success","output":output}),
        Err(error) => json!({"status":"error","error":format!("{error:#}")}),
    };
    let session_dir = runtime
        .session_dir()
        .context("persistent session missing")?
        .to_owned();
    ensure!(
        session_dir.starts_with(&root),
        "session escaped owned case directory"
    );
    let projection = SessionStore::open(session_dir.clone())?.load_projection()?;
    let history = runtime.history().await;
    let mut records = Vec::new();
    let mut receipt_checks = Vec::new();
    for record in &projection.records {
        records.push(json!({"schema_version":record.schema_version,"record_id":record.record_id,
            "session_seq":record.session_seq,"timestamp_ms":record.timestamp_ms,"session_id":record.session_id,
            "execution_id":record.execution_id,"thread_id":record.thread_id,"turn_id":record.turn_id,"entry":record.entry}));
        if let JournalEntry::ToolResultRecorded(value) = &record.entry {
            if value.result.call_id == VERIFY_ID {
                if let Some(receipt) = value.result.metadata.get(RECEIPT_KEY) {
                    let check = verify_receipt(receipt, &expected, &cwd, VERIFY_ID);
                    let effective_check = verify_receipt(receipt, &gate_expected, &cwd, VERIFY_ID);
                    let effective_error = effective_check.err().map(|error| format!("{error:#}"));
                    receipt_checks.push(match check {
                        Ok(()) => json!({"against":"original_compiled_policy","status":"valid","receipt":receipt,"effective_policy_error":effective_error}),
                        Err(error) => json!({"against":"original_compiled_policy","status":"invalid","error":format!("{error:#}"),"receipt":receipt}),
                    });
                }
            }
        }
    }
    write_json(&root.join("records.json"), &json!(records))?;
    write_json(&root.join("history.json"), &json!(history))?;
    write_json(
        &root.join("projection.json"),
        &json!({"history":projection.history,"history_revision":projection.history_revision,
        "interrupted_turns":projection.interrupted_turns,"interrupted_model_exchanges":projection.interrupted_model_exchanges,
        "interrupted_context_builds":projection.interrupted_context_builds,"unresolved_tool_calls":projection.unresolved_tool_calls,
        "unsettled_turns":projection.unsettled_turns}),
    )?;
    let file = cwd.join(RELATIVE_PATH);
    let observed = if file.exists() {
        Some(std::fs::read_to_string(file)?)
    } else {
        None
    };
    write_json(
        &root.join("report.json"),
        &json!({"scenario":scenario,"scope":"actual_agent_runtime_turn",
        "cwd":cwd,"session_id":runtime.session_id(),"session_dir":session_dir,"outcome":outcome,
        "approvals":approvals.snapshot(),"receipt_checks":receipt_checks,"observed_content":observed,
        "original_compiled_policy":original,"effective_gate_policy":gate_policy,"validation_status":"captured_requires_external_verifier"}),
    )?;
    drop(runtime);
    Ok(())
}
