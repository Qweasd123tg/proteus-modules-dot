//! Authored offline demonstration with a synthetic host; not a Core reader run.
use proteus_example_evidence_spans::{EvidenceSpans, TOOL_NAME, config::Config};
use proteus_module_sdk::{
    contracts::{
        contracts::{ExecutionAttribution, ProcessToolInvokeInput},
        domain::{ToolCall, ToolResult, new_execution_id},
        process_module::{ProcessModuleError, ToolModuleHost},
    },
    tool::ToolModule,
};
use serde_json::{Value, json};
struct FixtureHost;
impl ToolModuleHost for FixtureHost {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
    fn execute_tool_json(&self, raw: String) -> Result<String, ProcessModuleError> {
        let call: ToolCall = serde_json::from_str(&raw).unwrap();
        assert_eq!(call.name, "read_file");
        assert_eq!(call.args, json!({"path":"fixtures/source.txt"}));
        let text = include_str!("../fixtures/source.txt");
        Ok(serde_json::to_string(&ToolResult::ok(call.id,text).with_metadata(json!({
            "tool":"read_file","path":"/authored-fixture/fixtures/source.txt",
            "total_lines":text.lines().count(),"returned_lines":text.lines().count(),"truncated":false
        }))).unwrap())
    }
}
fn main() -> anyhow::Result<()> {
    let config: Config = serde_json::from_str(include_str!("../fixtures/config.json"))?;
    let mut args: Value = serde_json::from_str(include_str!("../fixtures/request.json"))?;
    if std::env::args().skip(1).any(|a| a == "--wrong-quote") {
        args["claims"][1]["quote"] = json!("éx"); // same UTF-8 byte count, different bytes.
    }
    let result = EvidenceSpans::new(config)?.invoke(
        ProcessToolInvokeInput {
            call: ToolCall::new("authored-quote-audit", TOOL_NAME, args),
            cwd: "/authored-fixture".into(),
            attribution: ExecutionAttribution::detached(new_execution_id()),
            skills: Default::default(),
        },
        &mut FixtureHost,
    )?;
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "host_kind":"synthetic_authored_fixture",
            "scope":"exact_quote_bytes_not_semantic_claim_truth",
            "result":result
        }))?
    );
    Ok(())
}
