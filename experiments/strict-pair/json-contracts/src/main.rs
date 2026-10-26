fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_example_json_contracts::load) {
        eprintln!("verification.json_contracts: {error:#}");
        std::process::exit(1);
    }
}
