//! Data-only resource-admission policy. No dispatch, permissions, reservations,
//! leases, timers, persistence, or readiness verification occur in this crate.
//!
//! All inputs must come from the trusted host. Names, revisions and ready facts
//! are assertions supplied by that host, not capabilities authenticated here.
//! The host must validate and atomically commit a proposal against current facts.

#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use std::fmt;

pub const HARD_MAX_PENDING: usize = 4_096;
pub const HARD_MAX_RESOURCES: usize = 4_096;
pub const HARD_MAX_DEMANDS: usize = 64;
pub const HARD_MAX_ID_BYTES: usize = 256;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Limits {
    pub max_pending: usize,
    pub max_resources: usize,
    pub max_demands_per_item: usize,
    pub max_id_bytes: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            max_pending: 256,
            max_resources: 256,
            max_demands_per_item: 16,
            max_id_bytes: 128,
        }
    }
}

impl Limits {
    fn validate(self) -> Result<(), QueueError> {
        let valid = self.max_pending > 0
            && self.max_pending <= HARD_MAX_PENDING
            && self.max_resources > 0
            && self.max_resources <= HARD_MAX_RESOURCES
            && self.max_demands_per_item > 0
            && self.max_demands_per_item <= HARD_MAX_DEMANDS
            && self.max_id_bytes > 0
            && self.max_id_bytes <= HARD_MAX_ID_BYTES;
        if valid {
            Ok(())
        } else {
            Err(QueueError::InvalidLimits)
        }
    }
}

/// Resource namespaces are distinct; names inside each namespace are byte-exact.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum ResourceKind {
    ProviderConcurrency,
    ProcessSlots,
    Exclusive,
    /// Optional conservative token-accounting units, never an exact money cost.
    TokenUpperBound,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct ResourceKey {
    pub kind: ResourceKind,
    pub name: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Demand {
    pub resource: ResourceKey,
    pub units: u64,
}

/// A host assertion only. Constructing this type does NOT verify readiness.
/// `invocation_id` must distinguish attempts, not merely name a workflow node.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HostReadyItem {
    pub invocation_id: String,
    pub ready_fact_revision: u64,
    pub demands: Vec<Demand>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Ticket {
    pub coordination_epoch: u128,
    pub sequence: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PendingItem {
    pub ticket: Ticket,
    pub enqueued_at_tick: u64,
    pub ready: HostReadyItem,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum QueueError {
    InvalidLimits,
    QueueFull,
    InvalidInvocationId,
    InvalidResourceId { demand_index: usize },
    EmptyDemands,
    TooManyDemands,
    ZeroDemand { demand_index: usize },
    ExclusiveDemandMustBeOne { demand_index: usize },
    DuplicateDemand,
    DuplicateInvocation,
    ClockWentBackwards,
    CounterExhausted,
    TooManyRemovals,
    DuplicateRemoval,
    UnknownTicket { ticket: Ticket },
}

impl fmt::Display for QueueError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for QueueError {}

/// Bounded pending data, not a scheduler or a durable execution journal.
/// Do not use parallel independent queues as independent resource authorities.
#[derive(Debug)]
pub struct PendingQueue {
    limits: Limits,
    coordination_epoch: u128,
    revision: u64,
    next_sequence: u64,
    latest_enqueue_tick: u64,
    items: Vec<PendingItem>,
}

impl PendingQueue {
    /// The host must never reuse an epoch after resetting counters or replacing
    /// the authoritative queue/resource coordinator; this crate generates no IDs.
    pub fn new(coordination_epoch: u128, limits: Limits) -> Result<Self, QueueError> {
        limits.validate()?;
        Ok(Self {
            limits,
            coordination_epoch,
            revision: 0,
            next_sequence: 0,
            latest_enqueue_tick: 0,
            items: Vec::new(),
        })
    }

    pub fn limits(&self) -> Limits {
        self.limits
    }

    pub fn coordination_epoch(&self) -> u128 {
        self.coordination_epoch
    }

    pub fn revision(&self) -> u64 {
        self.revision
    }

    /// Read-only view in stable enqueue order; demand lists are canonicalized.
    pub fn items(&self) -> &[PendingItem] {
        &self.items
    }

    /// Errors leave queue state unchanged. The host checks readiness before this
    /// call and again before committing any resulting plan.
    pub fn enqueue(
        &mut self,
        mut ready: HostReadyItem,
        now_tick: u64,
    ) -> Result<Ticket, QueueError> {
        if self.items.len() >= self.limits.max_pending {
            return Err(QueueError::QueueFull);
        }
        if now_tick < self.latest_enqueue_tick {
            return Err(QueueError::ClockWentBackwards);
        }
        if !valid_id(&ready.invocation_id, self.limits.max_id_bytes) {
            return Err(QueueError::InvalidInvocationId);
        }
        if ready.demands.is_empty() {
            return Err(QueueError::EmptyDemands);
        }
        if ready.demands.len() > self.limits.max_demands_per_item {
            return Err(QueueError::TooManyDemands);
        }
        for (index, demand) in ready.demands.iter().enumerate() {
            if !valid_id(&demand.resource.name, self.limits.max_id_bytes) {
                return Err(QueueError::InvalidResourceId { demand_index: index });
            }
            if demand.units == 0 {
                return Err(QueueError::ZeroDemand { demand_index: index });
            }
            if demand.resource.kind == ResourceKind::Exclusive && demand.units != 1 {
                return Err(QueueError::ExclusiveDemandMustBeOne { demand_index: index });
            }
        }
        ready.demands.sort_by(|a, b| a.resource.cmp(&b.resource));
        if ready.demands.windows(2).any(|pair| pair[0].resource == pair[1].resource) {
            return Err(QueueError::DuplicateDemand);
        }
        if self.items.iter().any(|item| item.ready.invocation_id == ready.invocation_id) {
            return Err(QueueError::DuplicateInvocation);
        }
        let next_sequence = self.next_sequence.checked_add(1).ok_or(QueueError::CounterExhausted)?;
        let next_revision = self.revision.checked_add(1).ok_or(QueueError::CounterExhausted)?;
        let ticket = Ticket {
            coordination_epoch: self.coordination_epoch,
            sequence: self.next_sequence,
        };
        // Re-own only validated lengths: a caller can provide a short String/Vec
        // with a very large spare capacity, which the queue must not retain.
        let ready = HostReadyItem {
            invocation_id: ready.invocation_id.as_str().to_owned(),
            ready_fact_revision: ready.ready_fact_revision,
            demands: ready.demands.iter().map(|demand| Demand {
                resource: ResourceKey {
                    kind: demand.resource.kind,
                    name: demand.resource.name.as_str().to_owned(),
                },
                units: demand.units,
            }).collect(),
        };
        self.items.push(PendingItem { ticket, enqueued_at_tick: now_tick, ready });
        self.next_sequence = next_sequence;
        self.revision = next_revision;
        self.latest_enqueue_tick = now_tick;
        Ok(ticket)
    }

    /// Idempotent pending cancellation. This does not stop a running owner or
    /// release resources. A successful removal invalidates outstanding proposals.
    pub fn cancel(&mut self, ticket: Ticket) -> Result<bool, QueueError> {
        if !self.items.iter().any(|item| item.ticket == ticket) {
            return Ok(false);
        }
        self.remove_pending(&[ticket])?;
        Ok(true)
    }

    /// Atomically removes this set from the in-memory queue, or changes nothing.
    /// For admitted items the host calls this only inside its own successful
    /// reservation transaction. This operation itself does NOT commit resources.
    pub fn remove_pending(&mut self, tickets: &[Ticket]) -> Result<usize, QueueError> {
        if tickets.len() > self.limits.max_pending {
            return Err(QueueError::TooManyRemovals);
        }
        for (index, ticket) in tickets.iter().enumerate() {
            if tickets[..index].contains(ticket) {
                return Err(QueueError::DuplicateRemoval);
            }
            if !self.items.iter().any(|item| item.ticket == *ticket) {
                return Err(QueueError::UnknownTicket { ticket: *ticket });
            }
        }
        if tickets.is_empty() {
            return Ok(0);
        }
        let next_revision = self.revision.checked_add(1).ok_or(QueueError::CounterExhausted)?;
        self.items.retain(|item| !tickets.contains(&item.ticket));
        self.revision = next_revision;
        Ok(tickets.len())
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceState {
    pub resource: ResourceKey,
    /// A host-configured upper ceiling; zero disables a non-exclusive resource.
    pub ceiling: u64,
    /// Already excludes active/reserved owners, including leases of lost owners
    /// that the host has not safely retired or fenced.
    pub available: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResourceSnapshot {
    pub coordination_epoch: u128,
    pub revision: u64,
    /// Host monotonic logical time; the unit is defined by the host adapter.
    /// Time is captured with the snapshot, never read from a system clock here.
    pub observed_at_tick: u64,
    pub resources: Vec<ResourceState>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PlanStamp {
    pub coordination_epoch: u128,
    pub queue_revision: u64,
    pub resource_revision: u64,
    pub observed_at_tick: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProposedGrant {
    pub ticket: Ticket,
    pub invocation_id: String,
    pub ready_fact_revision: u64,
    /// Complete, canonicalized demand list, not a partially satisfied request.
    pub demands: Vec<Demand>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DeferredReason {
    /// The first unavailable resource in canonical order; availability is local
    /// to this proposal after accounting for earlier complete grants.
    ResourceUnavailable { resource: ResourceKey, needed: u64, available: u64 },
    /// Intentional head-of-line blocking, including for disjoint resources.
    BehindAgedBarrier { blocked_ticket: Ticket },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DeferredItem {
    pub ticket: Ticket,
    pub reason: DeferredReason,
}

/// Proposal only. Public data is forgeable; neither this value nor its stamp is
/// a capability. Host validation remains mandatory for every policy implementation.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GrantPlan {
    pub stamp: PlanStamp,
    pub grants: Vec<ProposedGrant>,
    pub deferred: Vec<DeferredItem>,
    /// Canonical aggregate of every proposed grant. The host must reserve this
    /// entire set in one transaction, or reserve nothing and replan.
    pub total_reservations: Vec<Demand>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SnapshotProblem {
    InvalidResourceId,
    DuplicateResource,
    AvailableExceedsCeiling,
    ExclusiveCeilingMustBeOne,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AdmissionError {
    EpochMismatch,
    QueueRevisionExhausted,
    ResourceRevisionExhausted,
    ClockWentBackwards,
    TooManyResources,
    InvalidSnapshot { resource_index: usize, problem: SnapshotProblem },
    /// Actionable input rejection, NOT a temporary defer or aging barrier.
    UnknownResource { ticket: Ticket, resource: ResourceKey },
    /// Host must correct capacity/demand or remove/quarantine this item. No
    /// policy-approved plan is returned while this impossible item is present.
    DemandExceedsCeiling { ticket: Ticket, resource: ResourceKey, requested: u64, ceiling: u64 },
    ArithmeticOverflow,
}

impl fmt::Display for AdmissionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for AdmissionError {}

/// Replaceable pure decision boundary. Implementations must not interpret
/// caller/model DAG statuses as evidence and must not reserve or dispatch.
pub trait AdmissionPolicy {
    fn plan(
        &self,
        pending: &PendingQueue,
        resources: &ResourceSnapshot,
    ) -> Result<GrantPlan, AdmissionError>;
}

/// Stable FIFO scan with a host-time aging barrier. A young blocked item can be
/// bypassed; at/after this age it blocks ALL younger items. Zero means strict FIFO.
/// No resource is held for a deferred item. Progress still depends on the host
/// advancing time, retrying, and safely releasing actual owners.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AgingFifoPolicy {
    pub barrier_after_ticks: u64,
}

impl AdmissionPolicy for AgingFifoPolicy {
    fn plan(
        &self,
        pending: &PendingQueue,
        resources: &ResourceSnapshot,
    ) -> Result<GrantPlan, AdmissionError> {
        let capacities = validated_capacities(pending, resources)?;
        let mut remaining: BTreeMap<ResourceKey, u64> = capacities.iter()
            .map(|(key, state)| ((**key).clone(), state.available))
            .collect();
        let mut grants = Vec::new();
        let mut deferred = Vec::new();
        let mut barrier = None;

        for item in &pending.items {
            if let Some(blocked_ticket) = barrier {
                deferred.push(DeferredItem {
                    ticket: item.ticket,
                    reason: DeferredReason::BehindAgedBarrier { blocked_ticket },
                });
                continue;
            }
            let mut blocked = None;
            for demand in &item.ready.demands {
                let available = remaining.get(&demand.resource)
                    .copied().ok_or(AdmissionError::ArithmeticOverflow)?;
                if demand.units > available {
                    blocked = Some(DeferredReason::ResourceUnavailable {
                        resource: demand.resource.clone(),
                        needed: demand.units,
                        available,
                    });
                    break;
                }
            }
            if let Some(reason) = blocked {
                deferred.push(DeferredItem { ticket: item.ticket, reason });
                let age = resources.observed_at_tick.checked_sub(item.enqueued_at_tick)
                    .ok_or(AdmissionError::ClockWentBackwards)?;
                if age >= self.barrier_after_ticks {
                    barrier = Some(item.ticket);
                }
                continue;
            }

            // Only a complete feasible demand reaches this local, non-authoritative
            // debit. A later error discards the whole proposal, not a partial plan.
            for demand in &item.ready.demands {
                let available = remaining.get_mut(&demand.resource)
                    .ok_or(AdmissionError::ArithmeticOverflow)?;
                *available = available.checked_sub(demand.units)
                    .ok_or(AdmissionError::ArithmeticOverflow)?;
            }
            grants.push(ProposedGrant {
                ticket: item.ticket,
                invocation_id: item.ready.invocation_id.clone(),
                ready_fact_revision: item.ready.ready_fact_revision,
                demands: item.ready.demands.clone(),
            });
        }

        let mut total_reservations = Vec::new();
        for (key, state) in capacities {
            let available = remaining.get(key).copied().ok_or(AdmissionError::ArithmeticOverflow)?;
            let reserved = state.available.checked_sub(available).ok_or(AdmissionError::ArithmeticOverflow)?;
            if reserved != 0 {
                total_reservations.push(Demand { resource: key.clone(), units: reserved });
            }
        }
        Ok(GrantPlan {
            stamp: PlanStamp {
                coordination_epoch: pending.coordination_epoch,
                queue_revision: pending.revision,
                resource_revision: resources.revision,
                observed_at_tick: resources.observed_at_tick,
            },
            grants,
            deferred,
            total_reservations,
        })
    }
}

fn valid_id(id: &str, max_bytes: usize) -> bool {
    !id.is_empty() && id.len() <= max_bytes && !id.chars().any(char::is_control)
}

fn validated_capacities<'a>(
    pending: &PendingQueue,
    resources: &'a ResourceSnapshot,
) -> Result<BTreeMap<&'a ResourceKey, &'a ResourceState>, AdmissionError> {
    if resources.coordination_epoch != pending.coordination_epoch {
        return Err(AdmissionError::EpochMismatch);
    }
    if pending.revision == u64::MAX {
        return Err(AdmissionError::QueueRevisionExhausted);
    }
    if resources.revision == u64::MAX {
        return Err(AdmissionError::ResourceRevisionExhausted);
    }
    if resources.observed_at_tick < pending.latest_enqueue_tick {
        return Err(AdmissionError::ClockWentBackwards);
    }
    if resources.resources.len() > pending.limits.max_resources {
        return Err(AdmissionError::TooManyResources);
    }
    let mut capacities = BTreeMap::new();
    for (index, state) in resources.resources.iter().enumerate() {
        let problem = if !valid_id(&state.resource.name, pending.limits.max_id_bytes) {
            Some(SnapshotProblem::InvalidResourceId)
        } else if state.available > state.ceiling {
            Some(SnapshotProblem::AvailableExceedsCeiling)
        } else if state.resource.kind == ResourceKind::Exclusive && state.ceiling != 1 {
            Some(SnapshotProblem::ExclusiveCeilingMustBeOne)
        } else if capacities.contains_key(&state.resource) {
            Some(SnapshotProblem::DuplicateResource)
        } else {
            None
        };
        if let Some(problem) = problem {
            return Err(AdmissionError::InvalidSnapshot { resource_index: index, problem });
        }
        capacities.insert(&state.resource, state);
    }

    // Validate every item before selecting ANY grants. An impossible younger item
    // is also an actionable error, even if an older item would create a barrier.
    for item in &pending.items {
        for demand in &item.ready.demands {
            let state = capacities.get(&demand.resource).ok_or_else(|| AdmissionError::UnknownResource {
                ticket: item.ticket,
                resource: demand.resource.clone(),
            })?;
            if demand.units > state.ceiling {
                return Err(AdmissionError::DemandExceedsCeiling {
                    ticket: item.ticket,
                    resource: demand.resource.clone(),
                    requested: demand.units,
                    ceiling: state.ceiling,
                });
            }
        }
    }
    Ok(capacities)
}
