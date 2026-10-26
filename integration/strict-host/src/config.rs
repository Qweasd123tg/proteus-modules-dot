use anyhow::Result;
use proteus_core::core::AppConfig;
use proteus_strict_host_fixture::{MODEL_ID, POLICY_ID, VERIFIER};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

fn component(binary: &Path, exports: Value) -> Value {
    json!({"command":binary,"args":[],"env_allowlist":[],"handshake_timeout_ms":5000,"exports":exports})
}
pub fn make(
    scenario: &str,
    root: &Path,
    cwd: &Path,
    bins: &[PathBuf; 4],
    mut policy: Value,
) -> Result<AppConfig> {
    match scenario {
        "wrong_suite" => policy["expected"]["expected_suite_id"] = json!("different-suite"),
        "wrong_config" => policy["expected"]["expected_config_sha256"] = json!("0".repeat(64)),
        "missing_assertion" => policy["expected"]["documents"][0]["assertions"]
            .as_array_mut()
            .unwrap()
            .push(json!({"assertion_id":"extra-required","pointer":"/extra"})),
        _ => {}
    }
    let suite: Value = serde_json::from_str(include_str!("../fixtures/suite.json"))?;
    let mut value = json!({
        "active_provider":MODEL_ID,"providers":{MODEL_ID:{"provider":MODEL_ID,"model":MODEL_ID,"stream":true}},
        "agent_control":{"surface":"none"},"instructions":[],
        "modules":{"workflow":"coding.single_loop","context":"simple","policy":POLICY_ID,"hooks":["hermes.verify_evidence"]},
        "tools":{"enabled":["write_file","read_file",VERIFIER]},"permissions":{"mode":"normal"},
        "runtime":{"model_timeout_ms":10000,"context_timeout_ms":10000,"workflow_timeout_ms":30000},
        "event_log":{"path":root.join("events.jsonl"),"persist_deltas":false},
        "components":{
            "official":component(&bins[0],json!({"workflow":{"coding.single_loop":{"timeout_ms":30000}},"context":{"simple":{"timeout_ms":10000}},"tool":{"file_tools":{"timeout_ms":10000}}})),
            "fixture":component(&bins[1],json!({"model":{MODEL_ID:{"timeout_ms":10000}},"policy":{POLICY_ID:{"timeout_ms":5000}}})),
            "producer":component(&bins[2],json!({"tool":{VERIFIER:{"timeout_ms":10000}}})),
            "gate":component(&bins[3],json!({"hook":{"hermes.verify_evidence":{"timeout_ms":5000}}}))
        },
        "module_config":{
            "context":{"simple":{"search_provider":null,"memory_provider":null,"max_search_results":0}},
            "model":{MODEL_ID:{"scenario":if scenario=="omitted" {"write_then_stop"} else {"write_verify"}}},
            "policy":{POLICY_ID:{"cwd":cwd,"deny_reader":scenario=="read_denied"}},
            "tool":{VERIFIER:suite},
            "hook":{"hermes.verify_evidence":{"mutating_tools":["write_file"],"verification_tools":[VERIFIER],"max_nudges":1,"max_history_parts":50000,"on_exhaustion":"error","receipt_policy":policy}}
        }
    });
    if scenario == "default_deny" {
        // Separate direct admission probe; no model/workflow/hook histories invented.
        value["modules"] = json!({});
        value["providers"] = json!({});
        value["active_provider"] = Value::Null;
        value["components"] = json!({"official":component(&bins[0],json!({"tool":{"file_tools":{"timeout_ms":10000}}}))});
        value["module_config"] = json!({});
        value["tools"]["enabled"] = json!(["write_file"]);
    }
    Ok(serde_json::from_value(value)?)
}
