//! Authored offline probes for pinned rmcp, not a Proteus module or MCP server product.
pub mod fixture;

pub const LEGACY_VERSION: &str = "2025-11-25";
pub const MODERN_VERSION: &str = "2026-07-28";

pub fn rich_tool() -> serde_json::Value {
    serde_json::from_str(include_str!("../fixtures/rich-tool.json")).expect("authored JSON fixture")
}
