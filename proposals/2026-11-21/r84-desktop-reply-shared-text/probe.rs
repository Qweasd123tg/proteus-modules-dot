#![allow(dead_code, unused_imports)]
mod carrier;
mod declarative;
mod preferences;
mod transcript;
mod agents { pub mod codex; }
mod ui;
const APP_ID: &str = "fixture-r84";
fn main() {
    let stamp = env!("R84_REPLY_SOURCE_PROBE_ARM");
    eprintln!("ARM {stamp}");
    ui::run(stamp.ends_with("/candidate"));
}
