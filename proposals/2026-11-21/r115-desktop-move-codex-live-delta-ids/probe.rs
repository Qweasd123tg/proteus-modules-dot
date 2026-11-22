#![allow(dead_code, unused_imports)]
mod agents {
    pub mod codex;
}
mod transcript;
#[cfg(test)]
mod proof {
    include!("cases.rs");
}
#[cfg(test)]
include!("counter.rs");
