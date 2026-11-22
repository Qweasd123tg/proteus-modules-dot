#![allow(dead_code,unused_imports)]
use proteus_tabs as tabs;
mod agents { pub mod codex; }
mod attention;
mod conversations;
mod ledger;
mod ui;
fn main() {
    let stamp=env!("R83_CATALOG_PROBE_ARM");
    eprintln!("ARM {stamp}");
    ui::run(stamp.ends_with("/candidate"));
}
