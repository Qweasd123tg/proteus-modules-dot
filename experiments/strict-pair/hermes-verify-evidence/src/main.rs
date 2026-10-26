use proteus_example_hermes_verify_evidence::load;

fn main() {
    if let Err(error) = proteus_module_sdk::run(load) {
        eprintln!("hermes.verify_evidence: {error:#}");
        std::process::exit(1);
    }
}
