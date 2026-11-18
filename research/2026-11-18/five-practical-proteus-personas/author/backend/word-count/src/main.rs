use anyhow::{Result, bail};
use proteus_module_sdk::{
    contracts::{
        contracts::{
            ProcessComponentExportInitialize, ProcessToolDefinition, ProcessToolInvokeInput,
        },
        domain::ToolResult,
        process_module::ToolModuleHost,
    },
    tool::{ToolExport, ToolModule},
};
use proteus_word_count_example::{response, specification};
use serde::Deserialize;

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct Config {}

struct WordCount;

impl ToolModule for WordCount {
    fn definitions(&self) -> Vec<ProcessToolDefinition> {
        vec![ProcessToolDefinition {
            spec: specification(),
            model_visible: true,
            user_command: None,
        }]
    }

    fn invoke(
        &self,
        input: ProcessToolInvokeInput,
        host: &mut dyn ToolModuleHost,
    ) -> Result<ToolResult> {
        if host.is_cancelled()? {
            bail!("canceled");
        }
        response(input.call.id, &input.call.args)
    }
}

fn load(binding: ProcessComponentExportInitialize) -> Result<Box<dyn proteus_module_sdk::Export>> {
    if binding.slot != "tool" || binding.module_id != "example.word_count" {
        bail!("unsupported export {}/{}", binding.slot, binding.module_id);
    }
    let _: Config = serde_json::from_value(binding.module_config.clone())?;
    Ok(Box::new(ToolExport::new(binding, WordCount)?))
}

fn main() {
    if let Err(error) = proteus_module_sdk::run(load) {
        eprintln!("proteus-word-count-example: {error:#}");
        std::process::exit(1);
    }
}
