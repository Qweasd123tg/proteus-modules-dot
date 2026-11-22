#![allow(dead_code)]
mod types;
use types::*;
mod projection;
mod router {
    include!("router.rs");
    mod proof {
        use super::*;
        include!("cases.rs");
    }
}
include!("counter.rs");
