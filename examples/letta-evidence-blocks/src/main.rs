fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_example_letta_evidence_blocks::load) {
        eprintln!("letta.evidence_blocks: {error:#}");
        std::process::exit(1);
    }
}
