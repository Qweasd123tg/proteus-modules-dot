#![allow(dead_code, unused_imports)]
mod agents {
    pub mod codex;
}
mod ledger;
mod transcript;
mod ui;

fn main() {
    println!("ARM {}", env!("R71_PROBE_ARM"));
    ui::chat::history::diagnostic::run();
}
