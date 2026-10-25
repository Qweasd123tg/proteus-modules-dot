//! Reads existing canonical call/result records; it never parses assistant prose.
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};

use crate::{Config, receipt::passed_receipt};
use anyhow::{Result, ensure};
use proteus_module_sdk::contracts::model_standard::{
    CanonicalMessage, ContentPart, MessageRole, PartProvenance, PartScope,
};

#[derive(Debug, PartialEq, Eq)]
pub struct Evidence {
    pub saw_mutation: bool,
    pub fresh_verification: bool,
}

#[derive(Clone, Copy)]
enum Kind {
    Mutation,
    Verification,
    Other,
}

struct Pending {
    kind: Kind,
    started_message: usize,
}

pub fn inspect_history(
    history: &[CanonicalMessage],
    cwd: &Path,
    config: &Config,
    cancelled: &impl Fn() -> bool,
) -> Result<Evidence> {
    let mut pending = BTreeMap::<String, Pending>::new();
    let mut completed_relevant = BTreeSet::<String>::new();
    let mut part_ids = BTreeSet::new();
    let mut count = 0usize;
    let mut saw_mutation = false;
    let mut dirty_message = None;
    let mut verified_started = None;
    for (index, message) in history.iter().enumerate() {
        ensure!(!cancelled(), "verification gate canceled");
        for part in &message.parts {
            ensure!(!cancelled(), "verification gate canceled");
            count += 1;
            ensure!(
                count <= config.max_history_parts,
                "history exceeds configured evidence bound"
            );
            ensure!(
                part_ids.insert(part.part_id),
                "duplicate canonical part identity"
            );
            if part.scope != PartScope::Conversation {
                continue;
            }
            match &part.payload {
                ContentPart::ToolCall { call }
                    if message.role == MessageRole::Assistant
                        && part.provenance == PartProvenance::Model =>
                {
                    let kind = if config.mutating_tools.contains(&call.name) {
                        Kind::Mutation
                    } else if config.verification_tools.contains(&call.name) {
                        Kind::Verification
                    } else {
                        Kind::Other
                    };
                    // Track *all* call IDs: an unrelated pending call with the same ID
                    // must not donate its result to a verifier. Ambiguous IDs fail closed.
                    ensure!(
                        !pending.contains_key(&call.id),
                        "ambiguous pending call id {}",
                        call.id
                    );
                    if matches!(kind, Kind::Mutation) {
                        saw_mutation = true;
                        dirty_message = Some(index);
                    }
                    pending.insert(
                        call.id.clone(),
                        Pending {
                            kind,
                            started_message: index,
                        },
                    );
                    completed_relevant.remove(&call.id);
                }
                ContentPart::ToolResult { result }
                    if message.role == MessageRole::Tool
                        && part.provenance == PartProvenance::Tool =>
                {
                    let Some(call) = pending.remove(&result.call_id) else {
                        ensure!(
                            !completed_relevant.contains(&result.call_id),
                            "duplicate tool result for {}",
                            result.call_id
                        );
                        continue;
                    };
                    if let Some(owner) = &message.tool_call_id {
                        ensure!(
                            owner == &result.call_id,
                            "tool message/result identity mismatch"
                        );
                    }
                    if !matches!(call.kind, Kind::Other) {
                        completed_relevant.insert(result.call_id.clone());
                    }
                    match call.kind {
                        // A failed mutator may have partially changed files: success is not required.
                        Kind::Mutation => dirty_message = Some(index),
                        Kind::Verification
                            if passed_receipt(result, cwd, &config.receipt_policy) =>
                        {
                            if dirty_message.is_some_and(|dirty| call.started_message > dirty)
                                && !pending.values().any(|p| matches!(p.kind, Kind::Mutation))
                            {
                                verified_started = Some(call.started_message);
                            }
                        }
                        // A later failed/malformed verifier invalidates earlier positive evidence.
                        Kind::Verification => {
                            if saw_mutation {
                                dirty_message = Some(index);
                            }
                        }
                        Kind::Other => {}
                    }
                }
                _ => {}
            }
        }
    }
    let fresh_verification = saw_mutation
        && pending.is_empty()
        && matches!((verified_started, dirty_message), (Some(verified), Some(dirty)) if verified > dirty);
    Ok(Evidence {
        saw_mutation,
        fresh_verification,
    })
}
