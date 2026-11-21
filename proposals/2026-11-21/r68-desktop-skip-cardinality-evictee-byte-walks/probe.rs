#![allow(dead_code, unused_imports)]
mod agents {
    pub mod codex;
}
mod ledger;
mod transcript;
mod ui;

fn main() {
    ui::chat::history::diagnostic::run();
}
