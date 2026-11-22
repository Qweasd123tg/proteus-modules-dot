#![allow(dead_code)]
mod types;
use types::*;
mod projection;
mod router {
    include!("router.rs");
    #[cfg(test)]
    mod proof {
        use super::*;
        include!("cases.rs");
    }
}
#[cfg(test)]
include!("counter.rs");
