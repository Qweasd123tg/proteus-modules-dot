fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_example_evidence_spans::load) {
        eprintln!("evidence.verify_spans: {error:#}");
        std::process::exit(1);
    }
}
