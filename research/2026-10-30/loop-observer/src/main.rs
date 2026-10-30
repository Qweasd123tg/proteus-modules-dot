fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_example_loop_observer::load) {
        eprintln!("loop_observer.repeated_result: {error:#}");
        std::process::exit(1);
    }
}
