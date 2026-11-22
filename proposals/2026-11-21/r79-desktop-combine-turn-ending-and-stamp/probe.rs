#![allow(dead_code, unused_imports)]
mod agents { pub mod codex; }
mod ledger;
mod transcript;
mod ui;
fn main() {
    let stamp = env!("R79_TURN_END_PROBE_ARM");
    eprintln!("ARM {stamp}");
    ui::chat::run(stamp.ends_with("/candidate"));
}
