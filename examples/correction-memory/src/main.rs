fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_example_correction_memory::load) {
        eprintln!("memory.correction_cas: {error:#}");
        std::process::exit(1);
    }
}
