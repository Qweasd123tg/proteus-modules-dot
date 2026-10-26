fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_example_portable_skill_catalog::load) {
        eprintln!("portable.skills: {error:#}");
        std::process::exit(1);
    }
}
