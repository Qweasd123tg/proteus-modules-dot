use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ModelQuotaSnapshot {
    /// Time the provider response was obtained, including when served from cache.
    pub observed_at: u64,
    pub plan: Option<String>,
    pub buckets: Vec<ModelQuotaBucket>,
    pub credits: Option<ModelQuotaCredits>,
    /// Provider notices about partially unavailable account metadata.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub notices: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ModelQuotaBucket {
    pub id: String,
    pub name: Option<String>,
    pub allowed: Option<bool>,
    pub limit_reached: Option<bool>,
    pub windows: Vec<ModelQuotaWindow>,
    /// Additional account resources whose applicability to the active model is
    /// unknown. They must not determine its remaining allowance.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub informational: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ModelQuotaWindow {
    pub id: String,
    /// May exceed 100 when the provider reports overage; never inferred from tokens.
    pub used_percent: f64,
    pub duration_seconds: Option<u64>,
    /// Unix timestamp in seconds; null means the provider did not report it.
    pub resets_at: Option<u64>,
    /// Absolute usage in a provider-reported unit, when available.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub amount: Option<ModelQuotaAmount>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ModelQuotaAmount {
    pub used: f64,
    pub limit: f64,
    /// For example, USD. No currency conversion or token-based estimation.
    pub unit: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ModelQuotaCredits {
    pub available: bool,
    pub unlimited: bool,
    /// Provider-denominated decimal amount. No currency conversion or cost estimate.
    pub balance: Option<String>,
}
