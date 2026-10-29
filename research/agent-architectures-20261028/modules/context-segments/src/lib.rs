//! Source-only prototype, NOT an installed Proteus hook or Core adapter.
//!
//! Computes structural boundaries over host-normalized metadata. It never reads
//! message bodies, selects a retention budget, summarizes, drops, or reorders
//! history. Unknown or incomplete input yields no usable plan.
//!
//! A successful plan is conditional on the host's complete, truthful metadata.
//! Provider validation, immutable identity checks, anchors, and atomic application
//! against the same snapshot remain the host's responsibility.

#![forbid(unsafe_code)]

use std::collections::{btree_map::Entry, BTreeMap, BTreeSet};
use std::ops::Range;

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct EventId(pub u64);

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct CallId(pub u64);

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct GroupId(pub u64);

/// Opaque host-issued identity for one immutable model-view snapshot.
/// This is echoed, not authenticated; it is not a content hash or a CAS operation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SnapshotId(pub u128);

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Completeness {
    Complete,
    Incomplete,
    Unknown,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ProviderCoverage {
    /// The adapter identified ALL cross-event provider preservation constraints,
    /// including signed/reasoning/opaque loops, for this concrete provider view.
    HostVerified,
    Unknown,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum GroupKind {
    /// All messages originating from one complete assistant response/batch.
    AssistantBatch,
    /// A host-verified indivisible provider block or complete reasoning/tool loop.
    ProviderAtomic,
    /// An additional indivisible group imposed by the host.
    HostAtomic,
    Unknown,
}

/// Declaration refers to event memberships, not to the number of content parts.
/// `Complete` asserts that there are no members outside this snapshot. A count
/// alone cannot establish that; the adapter must obtain it from trusted state.
#[derive(Clone, Copy, Debug)]
pub struct Group {
    pub id: GroupId,
    pub kind: GroupKind,
    pub completeness: Completeness,
    pub expected_members: usize,
}

/// Payload-free descriptors for ALL parts in a complete canonical message.
/// No text, tool arguments/results, signatures, or provider bytes are accepted.
#[derive(Clone, Copy, Debug)]
pub enum Part {
    /// A recognized ordinary part with no additional preservation obligation.
    /// Unknown/provider-specific semantics must never fall back to this variant.
    Plain,
    ToolCall { call: CallId, batch: GroupId },
    /// One final canonical observation, including an error/cancellation result.
    /// Streaming chunks must NOT each be normalized as a final result.
    ToolResult { call: CallId },
    /// The group must encompass the entire provider preservation obligation,
    /// not just the reasoning block if a subsequent tool loop is also bound.
    Reasoning { group: GroupId },
    Opaque { group: GroupId },
    /// Unrecognized semantics are never silently treated as ordinary text.
    Unknown,
}

/// One indivisible canonical message, in unchanged model-view order.
/// A host must not split a message into events to create extra boundaries.
#[derive(Clone, Copy, Debug)]
pub struct Event<'a> {
    pub id: EventId,
    pub parts: &'a [Part],
    pub groups: &'a [GroupId],
}

#[derive(Clone, Copy, Debug)]
pub struct History<'a> {
    pub snapshot: SnapshotId,
    pub events: &'a [Event<'a>],
    pub groups: &'a [Group],
    /// Complete normalization of this closed projection, including every part
    /// and any dependency crossing the projection's edge. Not a random window.
    pub normalization: Completeness,
    pub provider_coverage: ProviderCoverage,
}

#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub events: usize,
    pub parts: usize,
    pub parts_per_event: usize,
    pub groups: usize,
    pub memberships: usize,
    pub memberships_per_event: usize,
    pub diagnostics: usize,
}

/// Configurations may lower these caps, never raise them. Input metadata itself
/// is allocated by the host; these limits bound policy work and extra storage.
pub const HARD_LIMITS: Limits = Limits {
    events: 16_384,
    parts: 131_072,
    parts_per_event: 1_024,
    groups: 32_768,
    memberships: 131_072,
    memberships_per_event: 256,
    diagnostics: 128,
};

impl Default for Limits {
    fn default() -> Self {
        Self {
            events: 4_096,
            parts: 32_768,
            parts_per_event: 512,
            groups: 8_192,
            memberships: 32_768,
            memberships_per_event: 128,
            diagnostics: 64,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LimitName {
    Events,
    Parts,
    PartsPerEvent,
    Groups,
    Memberships,
    MembershipsPerEvent,
    Diagnostics,
}

/// Typed, bounded diagnostics contain only numeric identities and positions.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum DiagnosticKind {
    InvalidLimit { name: LimitName, requested: usize, hard_cap: usize },
    LimitExceeded { name: LimitName, observed: usize, limit: usize },
    NormalizationNotComplete { state: Completeness },
    ProviderCoverageUnknown,
    DuplicateEvent { id: EventId, first_event: usize },
    DuplicateGroup { id: GroupId },
    UnknownGroupKind { id: GroupId },
    GroupNotComplete { id: GroupId, state: Completeness },
    InvalidMemberCount { id: GroupId, declared: usize, event_count: usize },
    DuplicateMembership { id: GroupId },
    UndeclaredGroup { id: GroupId },
    MissingMembership { id: GroupId },
    WrongGroupKind { id: GroupId, expected: GroupKind, actual: GroupKind },
    EmptyGroup { id: GroupId },
    MemberCountMismatch { id: GroupId, declared: usize, observed: usize },
    UnknownPart,
    DuplicateCall { id: CallId, first_event: usize },
    DuplicateResult { id: CallId, first_event: usize },
    MissingResult { id: CallId },
    MissingCall { id: CallId },
    ResultNotAfterCall { id: CallId, call_event: usize, result_event: usize },
    InternalEmptyCallIndex { id: CallId },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Diagnostic {
    pub kind: DiagnosticKind,
    pub event_index: Option<usize>,
    pub part_index: Option<usize>,
}

#[derive(Debug)]
pub struct Rejection {
    pub snapshot: SnapshotId,
    pub diagnostics: Vec<Diagnostic>,
    /// Saturating count of additional diagnostics omitted by the configured cap.
    /// Truncating diagnostics NEVER converts a rejection into a successful plan.
    pub suppressed_diagnostics: usize,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Protection {
    ToolPair(CallId),
    AtomicGroup { id: GroupId, kind: GroupKind },
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProtectedSpan {
    /// Half-open event interval [start, end). No boundary strictly inside it is
    /// allowed. Gaps between nonadjacent members are deliberately protected too.
    pub events: Range<usize>,
    pub reason: Protection,
}

#[derive(Debug)]
pub struct SegmentPlan {
    pub snapshot: SnapshotId,
    pub event_count: usize,
    /// Boundary b means events[..b] | events[b..]. Includes 0 and event_count.
    /// Structural legality is NOT permission to delete either side of a cut.
    pub legal_boundaries: Vec<usize>,
    /// Adjacent, nonempty, indivisible intervals covering the original view once
    /// in the original order. Empty history has no segments and one boundary (0).
    pub segments: Vec<Range<usize>>,
    /// Original constraints; overlaps are resolved by the boundary sweep.
    pub protected_spans: Vec<ProtectedSpan>,
}

impl SegmentPlan {
    pub fn is_legal_boundary(&self, boundary: usize) -> bool {
        self.legal_boundaries.binary_search(&boundary).is_ok()
    }
}

struct Diagnostics {
    snapshot: SnapshotId,
    cap: usize,
    items: Vec<Diagnostic>,
    suppressed: usize,
}

impl Diagnostics {
    fn new(snapshot: SnapshotId, cap: usize) -> Self {
        Self { snapshot, cap, items: Vec::new(), suppressed: 0 }
    }

    fn add(&mut self, kind: DiagnosticKind, event: Option<usize>, part: Option<usize>) {
        if self.items.len() < self.cap {
            self.items.push(Diagnostic { kind, event_index: event, part_index: part });
        } else {
            self.suppressed = self.suppressed.saturating_add(1);
        }
    }

    fn any(&self) -> bool {
        !self.items.is_empty() || self.suppressed != 0
    }

    fn reject(self) -> Rejection {
        Rejection {
            snapshot: self.snapshot,
            diagnostics: self.items,
            suppressed_diagnostics: self.suppressed,
        }
    }
}

struct GroupState<'a> {
    spec: &'a Group,
    first: Option<usize>,
    last: usize,
    members: usize,
}

#[derive(Default)]
struct CallState {
    call: Option<usize>,
    result: Option<usize>,
}

/// Returns only structural metadata. Any ambiguity rejects the ENTIRE plan;
/// it does not return a supposedly safe prefix of an unverified history.
pub fn analyze(history: History<'_>, limits: Limits) -> Result<SegmentPlan, Rejection> {
    // Validate the diagnostic cap before using any caller-provided allocation cap.
    let mut diagnostics = Diagnostics::new(history.snapshot, HARD_LIMITS.diagnostics);
    validate_limits(limits, &mut diagnostics);
    if diagnostics.any() {
        return Err(diagnostics.reject());
    }
    diagnostics.cap = limits.diagnostics;
    preflight(&history, limits, &mut diagnostics);
    if diagnostics.any() {
        return Err(diagnostics.reject());
    }
    if history.normalization != Completeness::Complete {
        diagnostics.add(
            DiagnosticKind::NormalizationNotComplete { state: history.normalization },
            None,
            None,
        );
    }
    if history.provider_coverage != ProviderCoverage::HostVerified {
        diagnostics.add(DiagnosticKind::ProviderCoverageUnknown, None, None);
    }
    if diagnostics.any() {
        return Err(diagnostics.reject());
    }

    let mut groups = BTreeMap::new();
    for spec in history.groups {
        if spec.kind == GroupKind::Unknown {
            diagnostics.add(DiagnosticKind::UnknownGroupKind { id: spec.id }, None, None);
        }
        if spec.completeness != Completeness::Complete {
            diagnostics.add(
                DiagnosticKind::GroupNotComplete { id: spec.id, state: spec.completeness },
                None,
                None,
            );
        }
        if spec.expected_members == 0 || spec.expected_members > history.events.len() {
            diagnostics.add(
                DiagnosticKind::InvalidMemberCount {
                    id: spec.id,
                    declared: spec.expected_members,
                    event_count: history.events.len(),
                },
                None,
                None,
            );
        }
        match groups.entry(spec.id) {
            Entry::Vacant(slot) => {
                slot.insert(GroupState { spec, first: None, last: 0, members: 0 });
            }
            Entry::Occupied(_) => {
                diagnostics.add(DiagnosticKind::DuplicateGroup { id: spec.id }, None, None);
            }
        }
    }

    let mut event_ids = BTreeMap::new();
    let mut calls: BTreeMap<CallId, CallState> = BTreeMap::new();
    for (event_index, event) in history.events.iter().enumerate() {
        match event_ids.entry(event.id) {
            Entry::Vacant(slot) => { slot.insert(event_index); }
            Entry::Occupied(first) => {
                diagnostics.add(
                    DiagnosticKind::DuplicateEvent { id: event.id, first_event: *first.get() },
                    Some(event_index),
                    None,
                );
            }
        }
        let mut membership = BTreeSet::new();
        for id in event.groups {
            if !membership.insert(*id) {
                diagnostics.add(
                    DiagnosticKind::DuplicateMembership { id: *id }, Some(event_index), None,
                );
                continue;
            }
            match groups.get_mut(id) {
                Some(group) => {
                    group.first.get_or_insert(event_index);
                    group.last = event_index;
                    group.members += 1;
                }
                None => diagnostics.add(
                    DiagnosticKind::UndeclaredGroup { id: *id }, Some(event_index), None,
                ),
            }
        }
        for (part_index, part) in event.parts.iter().enumerate() {
            match *part {
                Part::Plain => {}
                Part::Unknown => diagnostics.add(
                    DiagnosticKind::UnknownPart, Some(event_index), Some(part_index),
                ),
                Part::ToolCall { call, batch } => {
                    require_group(
                        batch, GroupKind::AssistantBatch, &groups, &membership,
                        event_index, part_index, &mut diagnostics,
                    );
                    let state = calls.entry(call).or_default();
                    if let Some(first_event) = state.call {
                        diagnostics.add(
                            DiagnosticKind::DuplicateCall { id: call, first_event },
                            Some(event_index), Some(part_index),
                        );
                    } else {
                        state.call = Some(event_index);
                    }
                }
                Part::ToolResult { call } => {
                    let state = calls.entry(call).or_default();
                    if let Some(first_event) = state.result {
                        diagnostics.add(
                            DiagnosticKind::DuplicateResult { id: call, first_event },
                            Some(event_index), Some(part_index),
                        );
                    } else {
                        state.result = Some(event_index);
                    }
                }
                Part::Reasoning { group } | Part::Opaque { group } => {
                    require_group(
                        group, GroupKind::ProviderAtomic, &groups, &membership,
                        event_index, part_index, &mut diagnostics,
                    );
                }
            }
        }
    }

    let mut protected_spans = Vec::new();
    for (id, state) in calls {
        match (state.call, state.result) {
            (Some(call_event), Some(result_event)) if call_event < result_event => {
                protected_spans.push(ProtectedSpan {
                    events: call_event..result_event + 1,
                    reason: Protection::ToolPair(id),
                });
            }
            (Some(call_event), Some(result_event)) => diagnostics.add(
                DiagnosticKind::ResultNotAfterCall { id, call_event, result_event },
                Some(result_event), None,
            ),
            (Some(event), None) => diagnostics.add(
                DiagnosticKind::MissingResult { id }, Some(event), None,
            ),
            (None, Some(event)) => diagnostics.add(
                DiagnosticKind::MissingCall { id }, Some(event), None,
            ),
            // Entries currently always record a call or result. Still reject,
            // rather than silently permit a cut, if a future edit violates this.
            (None, None) => diagnostics.add(
                DiagnosticKind::InternalEmptyCallIndex { id }, None, None,
            ),
        }
    }
    for (id, group) in groups {
        if group.members != group.spec.expected_members {
            diagnostics.add(
                DiagnosticKind::MemberCountMismatch {
                    id, declared: group.spec.expected_members, observed: group.members,
                },
                None, None,
            );
        }
        match group.first {
            Some(start) => protected_spans.push(ProtectedSpan {
                events: start..group.last + 1,
                reason: Protection::AtomicGroup { id, kind: group.spec.kind },
            }),
            None => diagnostics.add(DiagnosticKind::EmptyGroup { id }, None, None),
        }
    }
    if diagnostics.any() {
        return Err(diagnostics.reject());
    }

    // Every span [s,e) blocks the boundary interval (s,e). Superimposing these
    // intervals computes transitive closure without repeatedly merging spans.
    // Fixed caps keep both indices and signed counters comfortably bounded.
    let mut delta = vec![0_i64; history.events.len() + 1];
    for span in &protected_spans {
        delta[span.events.start + 1] += 1;
        delta[span.events.end] -= 1;
    }
    let mut active = 0_i64;
    let mut legal_boundaries = Vec::new();
    for (boundary, change) in delta.into_iter().enumerate() {
        active += change;
        if active == 0 {
            legal_boundaries.push(boundary);
        }
    }
    let segments = legal_boundaries.windows(2).map(|pair| pair[0]..pair[1]).collect();
    Ok(SegmentPlan {
        snapshot: history.snapshot,
        event_count: history.events.len(),
        legal_boundaries,
        segments,
        protected_spans,
    })
}

fn require_group(
    id: GroupId,
    expected: GroupKind,
    groups: &BTreeMap<GroupId, GroupState<'_>>,
    membership: &BTreeSet<GroupId>,
    event: usize,
    part: usize,
    diagnostics: &mut Diagnostics,
) {
    match groups.get(&id) {
        None => diagnostics.add(
            DiagnosticKind::UndeclaredGroup { id }, Some(event), Some(part),
        ),
        Some(group) if group.spec.kind != expected => diagnostics.add(
            DiagnosticKind::WrongGroupKind { id, expected, actual: group.spec.kind },
            Some(event), Some(part),
        ),
        Some(_) => {}
    }
    if !membership.contains(&id) {
        diagnostics.add(
            DiagnosticKind::MissingMembership { id }, Some(event), Some(part),
        );
    }
}

fn validate_limits(limits: Limits, diagnostics: &mut Diagnostics) {
    let values = [
        (LimitName::Events, limits.events, HARD_LIMITS.events),
        (LimitName::Parts, limits.parts, HARD_LIMITS.parts),
        (LimitName::PartsPerEvent, limits.parts_per_event, HARD_LIMITS.parts_per_event),
        (LimitName::Groups, limits.groups, HARD_LIMITS.groups),
        (LimitName::Memberships, limits.memberships, HARD_LIMITS.memberships),
        (
            LimitName::MembershipsPerEvent,
            limits.memberships_per_event,
            HARD_LIMITS.memberships_per_event,
        ),
        (LimitName::Diagnostics, limits.diagnostics, HARD_LIMITS.diagnostics),
    ];
    for (name, requested, hard_cap) in values {
        if requested > hard_cap || (name == LimitName::Diagnostics && requested == 0) {
            diagnostics.add(
                DiagnosticKind::InvalidLimit { name, requested, hard_cap }, None, None,
            );
        }
    }
}

fn preflight(history: &History<'_>, limits: Limits, diagnostics: &mut Diagnostics) {
    for (name, observed, limit) in [
        (LimitName::Events, history.events.len(), limits.events),
        (LimitName::Groups, history.groups.len(), limits.groups),
    ] {
        if observed > limit {
            diagnostics.add(
                DiagnosticKind::LimitExceeded { name, observed, limit }, None, None,
            );
        }
    }
    // Do not scan an oversized outer slice, even to collect more diagnostics.
    if diagnostics.any() {
        return;
    }
    let mut parts = 0_usize;
    let mut memberships = 0_usize;
    for (index, event) in history.events.iter().enumerate() {
        parts = parts.saturating_add(event.parts.len());
        memberships = memberships.saturating_add(event.groups.len());
        for (name, observed, limit) in [
            (LimitName::PartsPerEvent, event.parts.len(), limits.parts_per_event),
            (LimitName::MembershipsPerEvent, event.groups.len(), limits.memberships_per_event),
            (LimitName::Parts, parts, limits.parts),
            (LimitName::Memberships, memberships, limits.memberships),
        ] {
            if observed > limit {
                diagnostics.add(
                    DiagnosticKind::LimitExceeded { name, observed, limit }, Some(index), None,
                );
            }
        }
        // Preflight rejects early; it never scans the oversized nested slices.
        if diagnostics.any() {
            return;
        }
    }
}
