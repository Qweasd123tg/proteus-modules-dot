#![allow(dead_code, unused_imports)]
#[cfg(test)]
use proteus_tabs as tabs;
#[cfg(test)]
include!("counter.rs");
#[cfg(test)]
mod ui {
    include!("cases.rs");
}
