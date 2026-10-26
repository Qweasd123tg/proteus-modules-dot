//! Runnable use-case demonstration. The host and read results are authored
//! fixtures, not a real Core/ToolRegistry run. Assertions and hashing are real.
use proteus_example_json_contracts::{JsonContracts, TOOL_NAME, config::Config};
use proteus_module_sdk::{
    contracts::{
        contracts::{ExecutionAttribution, ProcessToolInvokeInput},
        domain::{ToolCall, ToolResult, new_execution_id},
        process_module::{ProcessModuleError, ToolModuleHost},
    },
    tool::ToolModule,
};
use serde_json::json;

struct FixtureHost {
    fail: bool,
}
impl ToolModuleHost for FixtureHost {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
    fn execute_tool_json(&self, call: String) -> Result<String, ProcessModuleError> {
        let call: ToolCall = serde_json::from_str(&call).unwrap();
        assert_eq!(call.name, "read_file");
        assert_eq!(call.args, json!({"path":"fixtures/release.json"}));
        let source = include_str!("../fixtures/release.json");
        let text = if self.fail {
            source.replace("\"publish\": false", "\"publish\": true")
        } else {
            source.into()
        };
        Ok(serde_json::to_string(&ToolResult::ok(call.id,text.clone()).with_metadata(json!({
            "tool":"read_file","path":"/authored-fixture/fixtures/release.json","total_lines":text.lines().count(),"returned_lines":text.lines().count(),"truncated":false
        }))).unwrap())
    }
}
fn main() -> anyhow::Result<()> {
    let fail = std::env::args().skip(1).any(|arg| arg == "--fail");
    let config: Config = serde_json::from_str(include_str!("../fixtures/suite.json"))?;
    let module = JsonContracts::new(config)?;
    let result = module.invoke(
        ProcessToolInvokeInput {
            call: ToolCall::new("authored-example", TOOL_NAME, json!({})),
            cwd: "/authored-fixture".into(),
            attribution: ExecutionAttribution::detached(new_execution_id()),
            skills: Default::default(),
        },
        &mut FixtureHost { fail },
    )?;
    println!(
        "{}",
        serde_json::to_string_pretty(
            &json!({"host_kind":"synthetic_authored_fixture","result":result})
        )?
    );
    // A failed demonstration is still a successful demonstration, not a test pass.
    Ok(())
}
