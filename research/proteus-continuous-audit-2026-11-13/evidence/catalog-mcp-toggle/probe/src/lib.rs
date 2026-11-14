#![allow(dead_code,unused_imports)]
pub mod packages;
pub mod catalog;
pub mod settings {pub mod draft;pub mod addons;pub mod mcp;pub use draft::Draft;}
pub mod declarative {pub mod manifest {
 pub struct Manifest {pub id:String}
 pub fn parse(_: &str)->anyhow::Result<Manifest>{anyhow::bail!("unused extension edge")}
 pub fn load(_: &std::path::Path)->anyhow::Result<Manifest>{anyhow::bail!("unused extension edge")}
}}
