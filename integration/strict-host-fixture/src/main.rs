fn main() {
    if let Err(error) = proteus_module_sdk::run(proteus_strict_host_fixture::load) {
        eprintln!("proteus-strict-host-fixture: {error:#}");
        std::process::exit(1);
    }
}
