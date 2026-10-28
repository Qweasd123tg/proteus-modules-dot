fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_example_tool_schema_budget::load) {
        eprintln!("tool_selection.schema_budget: {error:#}");
        std::process::exit(1);
    }
}
