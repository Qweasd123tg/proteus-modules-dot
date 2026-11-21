#![allow(dead_code, unused_imports)]
mod carrier;
mod declarative;
mod ledger;
mod preferences;
mod ui;
const APP_ID: &str = "fixture-r81";
fn main() {
    let stamp = env!("R81_RENDERER_PROBE_ARM");
    eprintln!("ARM {stamp}");
    ui::run(stamp.ends_with("/candidate"));
}
