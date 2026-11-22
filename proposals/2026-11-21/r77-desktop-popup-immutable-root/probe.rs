#![allow(dead_code)]
use proteus_diff as diff;

mod declarative {
    pub mod control;
    pub mod graph;
    pub mod lanes;
    pub mod list;
    pub mod presentation;
    pub mod protocol;
    pub mod session;
    pub mod tree;
    pub mod widget;
    mod icons {
        pub fn lucide(_: &str) -> Option<()> { panic!("no icon fixtures in this gate") }
    }
    mod svg {
        pub fn validate(_: &str) -> anyhow::Result<()> { panic!("no SVG fixtures in this gate") }
    }
}
mod ui {
    include!("carrier.rs");
}
fn main() {
    ui::run();
}
