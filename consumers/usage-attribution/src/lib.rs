//! Pure app-side grouping of an existing Core usage snapshot.
//! No collection, journal access, pricing, provider calls, or authority grants.
use std::collections::{BTreeMap, HashSet};

use proteus_contracts::{
    contracts::ModelCallOrigin,
    domain::{
        ExchangeId, ModelRef, ModelRequestUsage, ModelUsageStatus, SessionId, SessionUsageSnapshot,
    },
    model_standard::TokenUsage,
};
use serde::Serialize;

pub const MAX_REQUESTS: usize = 4096;
pub const MAX_MODEL_BYTES: usize = 512;
pub const MAX_INPUT_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_OUTPUT_BYTES: usize = 2 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SummaryError(pub &'static str);

impl std::fmt::Display for SummaryError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.0)
    }
}
impl std::error::Error for SummaryError {}

#[derive(Debug, Clone, Serialize, PartialEq, Eq, Default)]
pub struct OptionalCategory {
    pub known_sum: Option<u64>,
    pub reported_exchanges: usize,
    /// All group exchanges minus reported exchanges, including missing whole usage.
    pub missing_exchanges: usize,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq, Default)]
pub struct UsageCounts {
    pub exchange_count: usize,
    pub usage_reported_exchanges: usize,
    pub usage_missing_exchanges: usize,
    /// Known subset only; inspect reporting counts before interpreting zero.
    pub known_input_tokens: u64,
    pub known_output_tokens: u64,
    pub known_total_tokens: u64,
    pub cached_input: OptionalCategory,
    pub cache_creation_input: OptionalCategory,
    pub reasoning_output: OptionalCategory,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct UsageGroup {
    pub origin: ModelCallOrigin,
    pub requested_model: ModelRef,
    pub status: ModelUsageStatus,
    pub counts: UsageCounts,
    pub missing_usage_exchange_ids: Vec<ExchangeId>,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct UnavailableDimensions {
    pub operation_owner: &'static str,
    pub provider_attempts: &'static str,
    pub retry_lineage: &'static str,
    pub serving_model: &'static str,
    pub currency_cost: &'static str,
    pub estimated_tokens: &'static str,
    pub budget_enforcement: &'static str,
    pub source_authentication: &'static str,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct UsageAttributionReport {
    pub schema_version: u32,
    pub source: &'static str,
    pub session_id: SessionId,
    pub source_revision: u64,
    pub recorded_model_exchanges: usize,
    pub totals: UsageCounts,
    pub groups: Vec<UsageGroup>,
    pub unavailable: UnavailableDimensions,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(tag = "availability", rename_all = "snake_case")]
pub enum PayloadReport {
    Available {
        report: UsageAttributionReport,
    },
    Unavailable {
        schema_version: u32,
        reason: &'static str,
    },
}

fn add(target: &mut u64, value: u64) -> Result<(), SummaryError> {
    *target = target
        .checked_add(value)
        .ok_or(SummaryError("usage sum overflow"))?;
    Ok(())
}

impl OptionalCategory {
    fn record(&mut self, value: Option<u32>) -> Result<(), SummaryError> {
        if let Some(value) = value {
            let sum = self.known_sum.get_or_insert(0);
            add(sum, u64::from(value))?;
            self.reported_exchanges += 1;
        } else {
            self.missing_exchanges += 1;
        }
        Ok(())
    }
}

impl UsageCounts {
    fn record(&mut self, usage: Option<&TokenUsage>) -> Result<(), SummaryError> {
        self.exchange_count += 1;
        if let Some(usage) = usage {
            self.usage_reported_exchanges += 1;
            add(&mut self.known_input_tokens, u64::from(usage.input_tokens))?;
            add(
                &mut self.known_output_tokens,
                u64::from(usage.output_tokens),
            )?;
            add(
                &mut self.known_total_tokens,
                u64::from(usage.input_tokens) + u64::from(usage.output_tokens),
            )?;
        } else {
            self.usage_missing_exchanges += 1;
        }
        self.cached_input
            .record(usage.and_then(|u| u.cached_input_tokens))?;
        self.cache_creation_input
            .record(usage.and_then(|u| u.cache_creation_input_tokens))?;
        self.reasoning_output
            .record(usage.and_then(|u| u.reasoning_output_tokens))?;
        Ok(())
    }
}

fn validate_producer_shape(row: &ModelRequestUsage) -> Result<(), SummaryError> {
    match row.status {
        ModelUsageStatus::Completed => {
            if row.finished_at_ms.is_none() {
                return Err(SummaryError("completed exchange lacks finished_at_ms"));
            }
            if row.finish_reason.is_none() {
                return Err(SummaryError("completed exchange lacks finish_reason"));
            }
        }
        ModelUsageStatus::Error => {
            if row.finished_at_ms.is_none() {
                return Err(SummaryError("error exchange lacks finished_at_ms"));
            }
            if row.finish_reason.is_some() {
                return Err(SummaryError("error exchange has finish_reason"));
            }
            if row.usage.is_some() {
                return Err(SummaryError("error exchange has usage"));
            }
        }
        ModelUsageStatus::Unfinished | ModelUsageStatus::Canceled | ModelUsageStatus::Timeout => {
            if row.finished_at_ms.is_some() {
                return Err(SummaryError("pending exchange has finished_at_ms"));
            }
            if row.finish_reason.is_some() {
                return Err(SummaryError("pending exchange has finish_reason"));
            }
            if row.usage.is_some() {
                return Err(SummaryError("pending exchange has usage"));
            }
        }
    }
    Ok(())
}

fn origin_key(origin: ModelCallOrigin) -> u8 {
    match origin {
        ModelCallOrigin::Direct => 0,
        ModelCallOrigin::Auxiliary => 1,
    }
}
fn status_key(status: ModelUsageStatus) -> u8 {
    match status {
        ModelUsageStatus::Unfinished => 0,
        ModelUsageStatus::Completed => 1,
        ModelUsageStatus::Error => 2,
        ModelUsageStatus::Canceled => 3,
        ModelUsageStatus::Timeout => 4,
    }
}

/// Summarizes only supplied typed data. This does not authenticate its producer,
/// validate a journal, refresh a session, or infer omitted dimensions.
pub fn summarize(snapshot: &SessionUsageSnapshot) -> Result<UsageAttributionReport, SummaryError> {
    if snapshot.requests.len() > MAX_REQUESTS {
        return Err(SummaryError("request count exceeds limit"));
    }
    // Complete validation before cloning any model strings or constructing groups.
    let mut ids = HashSet::with_capacity(snapshot.requests.len());
    for row in &snapshot.requests {
        if row.model.provider.len() > MAX_MODEL_BYTES {
            return Err(SummaryError("provider name exceeds byte limit"));
        }
        if row.model.model.len() > MAX_MODEL_BYTES {
            return Err(SummaryError("model name exceeds byte limit"));
        }
        if !ids.insert(row.exchange_id) {
            return Err(SummaryError("duplicate exchange id"));
        }
        validate_producer_shape(row)?;
    }
    let mut totals = UsageCounts::default();
    let mut groups: BTreeMap<(u8, String, String, u8), UsageGroup> = BTreeMap::new();
    for row in &snapshot.requests {
        let key = (
            origin_key(row.origin),
            row.model.provider.clone(),
            row.model.model.clone(),
            status_key(row.status),
        );
        let group = groups.entry(key).or_insert_with(|| UsageGroup {
            origin: row.origin,
            requested_model: row.model.clone(),
            status: row.status,
            counts: UsageCounts::default(),
            missing_usage_exchange_ids: Vec::new(),
        });
        group.counts.record(row.usage.as_ref())?;
        totals.record(row.usage.as_ref())?;
        if row.usage.is_none() {
            group.missing_usage_exchange_ids.push(row.exchange_id);
        }
    }
    let groups = groups
        .into_values()
        .map(|mut group| {
            group.missing_usage_exchange_ids.sort_unstable();
            group
        })
        .collect();
    Ok(UsageAttributionReport {
        schema_version: 1,
        source: "session_usage_snapshot",
        session_id: snapshot.session_id,
        source_revision: snapshot.revision,
        recorded_model_exchanges: snapshot.requests.len(),
        totals,
        groups,
        unavailable: UnavailableDimensions {
            operation_owner: "not_exposed_by_snapshot",
            provider_attempts: "not_observed",
            retry_lineage: "not_exposed_by_snapshot",
            serving_model: "not_exposed_by_snapshot",
            currency_cost: "not_computed",
            estimated_tokens: "not_computed",
            budget_enforcement: "none",
            source_authentication: "not_evaluated",
        },
    })
}

/// The caller chooses the existing usage API's payload, not its response envelope.
pub fn decode_payload(bytes: &[u8]) -> Result<PayloadReport, SummaryError> {
    if bytes.len() > MAX_INPUT_BYTES {
        return Err(SummaryError("input exceeds byte limit"));
    }
    let snapshot: Option<SessionUsageSnapshot> = serde_json::from_slice(bytes)
        .map_err(|_| SummaryError("invalid usage snapshot payload"))?;
    match snapshot {
        Some(snapshot) => Ok(PayloadReport::Available {
            report: summarize(&snapshot)?,
        }),
        None => Ok(PayloadReport::Unavailable {
            schema_version: 1,
            reason: "snapshot_not_available",
        }),
    }
}

/// Serialize completely before the caller emits success; oversize produces no partial report.
pub fn encode_report(report: &PayloadReport) -> Result<Vec<u8>, SummaryError> {
    let mut bytes =
        serde_json::to_vec(report).map_err(|_| SummaryError("report serialization failed"))?;
    bytes.push(b'\n');
    if bytes.len() > MAX_OUTPUT_BYTES {
        return Err(SummaryError("output exceeds byte limit"));
    }
    Ok(bytes)
}
