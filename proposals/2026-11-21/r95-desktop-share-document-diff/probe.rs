#![allow(dead_code, unused_imports)]
extern crate self as gpui_kit;
use proteus_diff as diff;
mod ui {pub mod diff {pub(crate) use super::super::model::DiffView;}}
pub(crate) use model::component;
pub mod assets {
    // Only declared fixture icons; production lookup and error logic are compiled.
    #[derive(Clone, Copy)]
    pub struct IconName(&'static str);
    impl IconName {
        pub const ALL: &'static [Self] = &[Self("icons/git-branch.svg"), Self("icons/file-code.svg")];
        pub fn path(self) -> &'static str { self.0 }
    }
}
mod declarative {
    pub mod control;
    pub mod graph;
    pub mod icons;
    pub mod lanes;
    pub mod list;
    pub mod presentation;
    pub mod protocol;
    pub mod session;
    pub mod tree;
    pub mod widget;
    mod svg {
        pub fn validate(_: &str) -> anyhow::Result<()> { panic!("SVG is out of scope") }
    }
}
mod model { include!("carrier.rs"); }
fn main() { model::run(); }
