#![allow(dead_code, unused_imports)]
pub use proteus_contracts::{domain, model_standard};
pub mod agents { #[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/agents/codex/mod.rs"] pub mod codex; }
#[path = "/workspace/scratch/3ba0fff8d310/desktop-behaviour/src/transcript/mod.rs"] mod transcript;
mod core_projection;
#[cfg(test)] mod audit;
#[cfg(test)] mod copy_probe;
