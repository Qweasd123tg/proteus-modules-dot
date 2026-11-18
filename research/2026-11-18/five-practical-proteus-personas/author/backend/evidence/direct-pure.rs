// A fallback for testing the authored library against an already compiled public contracts crate;
// this does not claim to compile the prescribed SDK, and it never enters a worker or creates a host.
extern crate self as proteus_module_sdk;
pub mod contracts { pub use proteus_contracts::*; }
#[path = "../word-count/src/lib.rs"]
mod authored;
