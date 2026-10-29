//! Bounded, host-owned speculative compaction candidates; not a Proteus hook.
//!
//! This component neither starts jobs nor edits history. A trusted session owner
//! serializes all calls and implements [`HostTransaction`] with the real operation
//! gate, authoritative history and durable checkpoint transaction. An observation
//! is not a lock. The trait's contract is necessary, not enforced by this crate.
//!
//! Cancellation is an intent. A dispatched candidate retains its capacity until
//! [`CandidateOwner::finish`] reports physical settlement. An uncertain history
//! commit retains capacity until durable reconciliation; it is never retried.

#![forbid(unsafe_code)]

/// Opaque, domain-separated cryptographic digest computed by the trusted host.
/// No hashing algorithm or serialization is silently selected by this crate.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Digest(pub [u8; 32]);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SessionIdentity {
    pub session: [u8; 16],
    /// Fresh for each reconstructed owner; never reuse for late callbacks.
    pub incarnation: [u8; 16],
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Epochs {
    /// Changes on history reset/rewrite/adoption, but not ordinary suffix append.
    pub history: u64,
    pub configuration: u64,
    pub policy: u64,
}

/// Host fingerprints include concrete revisions, not merely friendly names.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ContextIdentity {
    pub provider: Digest,
    pub model: Digest,
    pub workflow: Digest,
    pub instructions: Digest,
    pub epochs: Epochs,
}

/// Identity of exactly the replaceable prefix, excluding the growing live tail.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PrefixIdentity {
    pub message_count: u64,
    pub first_message: [u8; 16],
    pub last_message: [u8; 16],
    /// Must cover message identities, roles, contents, attachments and tool links.
    pub digest: Digest,
}

/// Captured by the session owner, never accepted back from the model as authority.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SourceSnapshot {
    pub session: SessionIdentity,
    pub context: ContextIdentity,
    pub prefix: PrefixIdentity,
    pub history_revision: u64,
    /// Declared bytes of the immutable worker snapshot/request, including anchors.
    /// The host must enforce this at capture/transport; it is not measured here.
    pub snapshot_bytes: usize,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Operations {
    pub active_model_calls: usize,
    pub active_tool_calls: usize,
    pub model_stream_open: bool,
    pub execution_cancelled: bool,
}

impl Operations {
    fn busy(self) -> bool {
        self.active_model_calls != 0
            || self.active_tool_calls != 0
            || self.model_stream_open
    }
}

/// Observed at the candidate's exact prefix boundary, not at the current tail.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HostObservation {
    pub session: SessionIdentity,
    pub context: ContextIdentity,
    /// None if that exact boundary is no longer present/valid.
    pub prefix: Option<PrefixIdentity>,
    pub history_revision: u64,
    pub operations: Operations,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StaleReason {
    Session,
    Provider,
    Model,
    Workflow,
    Instructions,
    HistoryEpoch,
    ConfigurationEpoch,
    PolicyEpoch,
    RevisionRegressed,
    Prefix,
}

/// Append-only tail growth is intentionally permitted. A revision regression,
/// rewritten prefix, incarnation/config/policy change is not.
pub fn compare_source(
    source: &SourceSnapshot,
    current: &HostObservation,
) -> Result<(), StaleReason> {
    if source.session != current.session {
        return Err(StaleReason::Session);
    }
    let a = source.context;
    let b = current.context;
    if a.provider != b.provider {
        return Err(StaleReason::Provider);
    }
    if a.model != b.model {
        return Err(StaleReason::Model);
    }
    if a.workflow != b.workflow {
        return Err(StaleReason::Workflow);
    }
    if a.instructions != b.instructions {
        return Err(StaleReason::Instructions);
    }
    if a.epochs.history != b.epochs.history {
        return Err(StaleReason::HistoryEpoch);
    }
    if a.epochs.configuration != b.epochs.configuration {
        return Err(StaleReason::ConfigurationEpoch);
    }
    if a.epochs.policy != b.epochs.policy {
        return Err(StaleReason::PolicyEpoch);
    }
    if current.history_revision < source.history_revision {
        return Err(StaleReason::RevisionRegressed);
    }
    if current.prefix != Some(source.prefix) {
        return Err(StaleReason::Prefix);
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Limits {
    /// 1 by default, at most 4. Includes reserved, running and uncertain commits.
    pub max_candidates: usize,
    pub max_snapshot_bytes: usize,
    pub max_replacement_bytes: usize,
    /// Reservations include snapshot plus maximum replacement until settlement.
    pub max_reserved_bytes: usize,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            max_candidates: 1,
            max_snapshot_bytes: 4 * 1024 * 1024,
            max_replacement_bytes: 128 * 1024,
            max_reserved_bytes: 4 * 1024 * 1024 + 128 * 1024,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error {
    InvalidLimits,
    Closed,
    ForeignSession,
    InvalidSnapshot,
    SnapshotTooLarge,
    Capacity,
    ByteCapacity,
    IdentifierExhausted,
    UnknownCandidate,
    WrongState,
}

/// A routing/idempotency key, not a grant of model or history authority.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct CandidateId {
    session: [u8; 16],
    incarnation: [u8; 16],
    sequence: u64,
}

impl CandidateId {
    pub fn session(self) -> [u8; 16] {
        self.session
    }

    pub fn incarnation(self) -> [u8; 16] {
        self.incarnation
    }

    pub fn sequence(self) -> u64 {
        self.sequence
    }
}

/// Exact counters when available. Unknown is not silently represented as zero.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Usage {
    Known { input_tokens: u64, output_tokens: u64 },
    Unknown,
}

/// In-memory audit counters only; the host owns durable billing/reconciliation.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct UsageTotals {
    pub input_tokens: u128,
    pub output_tokens: u128,
    pub settled_jobs: u128,
    pub unknown_usage_jobs: u128,
    /// Saturation is surfaced, never wrapped or treated as exact accounting.
    pub saturated: bool,
}

fn add_counter(total: &mut u128, amount: u128, saturated: &mut bool) {
    match total.checked_add(amount) {
        Some(value) => *total = value,
        None => {
            *total = u128::MAX;
            *saturated = true;
        }
    }
}

impl UsageTotals {
    fn record(&mut self, usage: Usage) {
        add_counter(&mut self.settled_jobs, 1, &mut self.saturated);
        match usage {
            Usage::Known { input_tokens, output_tokens } => {
                add_counter(&mut self.input_tokens, input_tokens.into(), &mut self.saturated);
                add_counter(&mut self.output_tokens, output_tokens.into(), &mut self.saturated);
            }
            Usage::Unknown => {
                add_counter(&mut self.unknown_usage_jobs, 1, &mut self.saturated);
            }
        }
    }
}

/// Opaque canonical replacement envelope: summary AND retained anchors. No
/// Clone implementation: the owner moves the bounded allocation, not a snapshot.
/// Host must validate message structure, anchors and actual provider budget.
pub enum WorkerResult {
    Completed(Box<[u8]>),
    Failed,
    Cancelled,
}

impl std::fmt::Debug for WorkerResult {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Completed(payload) => f.debug_struct("Completed")
                .field("replacement_bytes", &payload.len()).finish(),
            Self::Failed => f.write_str("Failed"),
            Self::Cancelled => f.write_str("Cancelled"),
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CancelReason {
    User,
    Superseded,
    Expired,
    Shutdown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CancelAction {
    /// No dispatched worker exists, or it was already settled.
    Discarded,
    /// Host must signal its owned worker; capacity is STILL held.
    SignalWorker,
    AlreadyRequested,
    /// A possibly committed transaction cannot be rolled back by cancellation.
    ReconcileCommit,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DiscardReason {
    Cancelled(CancelReason),
    ExecutionCancelled,
    Stale(StaleReason),
    Failed,
    WorkerCancelled,
    EmptyReplacement,
    ReplacementTooLarge,
    HostRejected(HostRejection),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FinishOutcome {
    Ready,
    Discarded(DiscardReason),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Reserved,
    Preparing,
    CancelRequested(CancelReason),
    Ready,
    CommitUnknown,
}

enum State {
    Reserved,
    Preparing,
    CancelRequested(CancelReason),
    Ready(Box<[u8]>),
    CommitUnknown { replacement: Box<[u8]>, observed_revision: u64 },
}

impl State {
    fn phase(&self) -> Phase {
        match self {
            Self::Reserved => Phase::Reserved,
            Self::Preparing => Phase::Preparing,
            Self::CancelRequested(reason) => Phase::CancelRequested(*reason),
            Self::Ready(_) => Phase::Ready,
            Self::CommitUnknown { .. } => Phase::CommitUnknown,
        }
    }
}

struct Entry {
    id: CandidateId,
    source: SourceSnapshot,
    state: State,
    charged_bytes: usize,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HostRejection {
    Busy,
    Cancelled,
    CompareFailed,
    OverBudget,
    InvalidReplacementOrAnchors,
    PersistenceFailedWithoutCommit,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CommitReceipt {
    pub history_revision: u64,
    pub retained_suffix_messages: u64,
}

/// Any error AFTER a write might have happened must become Unknown, not
/// NotCommitted. A timeout/cancelled future is not proof of rollback.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CommitResult {
    Committed(CommitReceipt),
    NotCommitted(HostRejection),
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ObservationError {
    /// No write was attempted; the ready candidate may be reconsidered later.
    Unavailable,
}

/// Borrowed only for the duration of a synchronous, host-owned transaction.
pub struct CommitRequest<'a> {
    pub idempotency_key: CandidateId,
    pub source: &'a SourceSnapshot,
    pub observed_revision: u64,
    pub replacement: &'a [u8],
}

/// REQUIRED HOST CONTRACT (a trait implementation is not proof of this):
///
/// * Hold Core's exclusive operation gate, reject active model/tool operations
///   and open streams, and serialize authoritative history/session transitions.
/// * Observe exactly source.prefix; accept append-only suffix growth only.
/// * At commit, atomically recheck source identity, prefix, observed revision,
///   cancellation, permissions, anchors and composed provider token budget.
/// * Replace only source.prefix, preserve the current suffix byte-for-byte and
///   checkpoint durably under the same transaction/idempotency key.
/// * Report Unknown for uncertain writes and reconcile from durable evidence.
///
/// No unchecked snapshot boolean may be used as a substitute for the gate.
/// An async Core adapter must keep this transaction semantics across its awaits;
/// this prototype does not supply such an adapter or extend invocation lifetime.
pub trait HostTransaction {
    fn observe(&mut self, source: &SourceSnapshot)
        -> Result<HostObservation, ObservationError>;

    fn compare_and_replace(&mut self, request: CommitRequest<'_>) -> CommitResult;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AdoptOutcome {
    Adopted(CommitReceipt),
    DeferredBusy,
    DeferredObservationUnavailable,
    Discarded(DiscardReason),
    /// No retry; host must query durable commit status using CandidateId.
    NeedsReconciliation,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reconciliation {
    Committed(CommitReceipt),
    /// Durable evidence confirms no mutation. Candidate is discarded, not retried.
    NotCommitted,
    StillUnknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReconcileOutcome {
    Adopted(CommitReceipt),
    Discarded,
    StillUnknown,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct ShutdownReport {
    pub cancel_workers: Vec<CandidateId>,
    pub reconcile_commits: Vec<CandidateId>,
}

/// One owner per session incarnation; owned by the host actor, never a hook.
/// No Clone, runtime, hidden worker, blocking mutex, network or history storage.
pub struct CandidateOwner {
    session: SessionIdentity,
    limits: Limits,
    next_sequence: u64,
    closed: bool,
    entries: Vec<Entry>,
    usage: UsageTotals,
}

impl std::fmt::Debug for CandidateOwner {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Never transitively format entries: replacements may include private
        // conversation text and retained anchors, including in uncertain commits.
        f.debug_struct("CandidateOwner")
            .field("closed", &self.closed)
            .field("candidate_count", &self.entries.len())
            .field("reserved_bytes", &self.reserved_bytes())
            .field("usage", &self.usage)
            .finish_non_exhaustive()
    }
}

impl CandidateOwner {
    pub fn new(session: SessionIdentity, limits: Limits) -> Result<Self, Error> {
        if !(1..=4).contains(&limits.max_candidates)
            || limits.max_snapshot_bytes == 0
            || limits.max_replacement_bytes == 0
            || limits.max_reserved_bytes == 0
            || limits.max_snapshot_bytes.checked_add(limits.max_replacement_bytes).is_none()
        {
            return Err(Error::InvalidLimits);
        }
        Ok(Self {
            session,
            limits,
            next_sequence: 1,
            closed: false,
            entries: Vec::with_capacity(limits.max_candidates),
            usage: UsageTotals::default(),
        })
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn is_closed(&self) -> bool {
        self.closed
    }

    pub fn reserved_bytes(&self) -> usize {
        // Admission ensures the sum never exceeds the configured usize bound.
        self.entries.iter().map(|entry| entry.charged_bytes).sum()
    }

    pub fn usage(&self) -> UsageTotals {
        self.usage
    }

    pub fn phase(&self, id: CandidateId) -> Result<Phase, Error> {
        Ok(self.entries[self.index(id)?].state.phase())
    }

    fn index(&self, id: CandidateId) -> Result<usize, Error> {
        self.entries.iter().position(|entry| entry.id == id).ok_or(Error::UnknownCandidate)
    }

    /// Reserve BEFORE snapshot materialization/worker launch. The trusted host
    /// first obtains a bounded size and immutable identity in its capture boundary.
    /// This method does not grant permission to call a model or prepare_context.
    pub fn reserve(&mut self, source: SourceSnapshot) -> Result<CandidateId, Error> {
        if self.closed {
            return Err(Error::Closed);
        }
        if source.session != self.session {
            return Err(Error::ForeignSession);
        }
        if source.prefix.message_count == 0 || source.snapshot_bytes == 0 {
            return Err(Error::InvalidSnapshot);
        }
        if source.snapshot_bytes > self.limits.max_snapshot_bytes {
            return Err(Error::SnapshotTooLarge);
        }
        if self.entries.len() == self.limits.max_candidates {
            return Err(Error::Capacity);
        }
        let charged_bytes = source.snapshot_bytes
            .checked_add(self.limits.max_replacement_bytes).ok_or(Error::ByteCapacity)?;
        let total = self.reserved_bytes().checked_add(charged_bytes).ok_or(Error::ByteCapacity)?;
        if total > self.limits.max_reserved_bytes {
            return Err(Error::ByteCapacity);
        }
        let next = self.next_sequence.checked_add(1).ok_or(Error::IdentifierExhausted)?;
        let id = CandidateId {
            session: self.session.session,
            incarnation: self.session.incarnation,
            sequence: self.next_sequence,
        };
        self.next_sequence = next;
        self.entries.push(Entry { id, source, state: State::Reserved, charged_bytes });
        Ok(id)
    }

    /// Mark BEFORE dispatch. Failure after this transition must settle via finish,
    /// even if the worker never reached the provider. Do not recreate an uncertain
    /// dispatch as a second job. The host owns job handles and transport bounds.
    pub fn mark_dispatched(&mut self, id: CandidateId) -> Result<(), Error> {
        let index = self.index(id)?;
        if self.entries[index].state.phase() != Phase::Reserved {
            return Err(Error::WrongState);
        }
        self.entries[index].state = State::Preparing;
        Ok(())
    }

    pub fn cancel(&mut self, id: CandidateId, reason: CancelReason) -> Result<CancelAction, Error> {
        let index = self.index(id)?;
        match self.entries[index].state.phase() {
            Phase::Reserved | Phase::Ready => {
                self.entries.remove(index);
                Ok(CancelAction::Discarded)
            }
            Phase::Preparing => {
                self.entries[index].state = State::CancelRequested(reason);
                Ok(CancelAction::SignalWorker)
            }
            Phase::CancelRequested(_) => Ok(CancelAction::AlreadyRequested),
            Phase::CommitUnknown => Ok(CancelAction::ReconcileCommit),
        }
    }

    /// Report exactly ONE terminal settlement, after the worker/network request
    /// cannot produce another candidate or host callback and its snapshot buffers
    /// are released. Cancel ACK is insufficient.
    /// Accepted usage is counted even if the result is stale/failed/cancelled/large.
    /// Duplicate or foreign callbacks cannot change counters or release a new slot.
    ///
    /// current is freshly read by the host at this candidate's prefix boundary.
    /// Busy operations do not prevent storing a ready result; adoption still waits.
    pub fn finish(
        &mut self,
        id: CandidateId,
        result: WorkerResult,
        usage: Usage,
        current: &HostObservation,
    ) -> Result<FinishOutcome, Error> {
        let index = self.index(id)?;
        let cancellation = match self.entries[index].state.phase() {
            Phase::Preparing => None,
            Phase::CancelRequested(reason) => Some(reason),
            _ => return Err(Error::WrongState),
        };
        self.usage.record(usage);
        let source = self.entries[index].source;
        let reject = if let Some(reason) = cancellation {
            Some(DiscardReason::Cancelled(reason))
        } else if current.operations.execution_cancelled {
            Some(DiscardReason::ExecutionCancelled)
        } else {
            compare_source(&source, current).err().map(DiscardReason::Stale)
        };
        if let Some(reason) = reject {
            self.entries.remove(index);
            return Ok(FinishOutcome::Discarded(reason));
        }
        let payload = match result {
            WorkerResult::Completed(payload) if payload.is_empty() => {
                self.entries.remove(index);
                return Ok(FinishOutcome::Discarded(DiscardReason::EmptyReplacement));
            }
            WorkerResult::Completed(payload) if payload.len() > self.limits.max_replacement_bytes => {
                self.entries.remove(index);
                return Ok(FinishOutcome::Discarded(DiscardReason::ReplacementTooLarge));
            }
            WorkerResult::Completed(payload) => payload,
            WorkerResult::Failed => {
                self.entries.remove(index);
                return Ok(FinishOutcome::Discarded(DiscardReason::Failed));
            }
            WorkerResult::Cancelled => {
                self.entries.remove(index);
                return Ok(FinishOutcome::Discarded(DiscardReason::WorkerCancelled));
            }
        };
        self.entries[index].charged_bytes = payload.len();
        self.entries[index].state = State::Ready(payload);
        Ok(FinishOutcome::Ready)
    }

    /// The host must already own a real transaction when supplying txn. A ready
    /// candidate cannot authorize concurrent history replacement by itself.
    pub fn try_adopt<T: HostTransaction>(
        &mut self,
        id: CandidateId,
        txn: &mut T,
    ) -> Result<AdoptOutcome, Error> {
        let index = self.index(id)?;
        match self.entries[index].state.phase() {
            Phase::CommitUnknown => return Ok(AdoptOutcome::NeedsReconciliation),
            Phase::Ready => {}
            _ => return Err(Error::WrongState),
        }
        let source = self.entries[index].source;
        let observation = match txn.observe(&source) {
            Ok(value) => value,
            Err(ObservationError::Unavailable) => return Ok(AdoptOutcome::DeferredObservationUnavailable),
        };
        if let Err(reason) = compare_source(&source, &observation) {
            self.entries.remove(index);
            return Ok(AdoptOutcome::Discarded(DiscardReason::Stale(reason)));
        }
        if observation.operations.execution_cancelled {
            self.entries.remove(index);
            return Ok(AdoptOutcome::Discarded(DiscardReason::ExecutionCancelled));
        }
        if observation.operations.busy() {
            return Ok(AdoptOutcome::DeferredBusy);
        }
        // Fence BEFORE crossing the host's mutating boundary. Even a panic
        // caught by the embedding host must not leave this candidate retryable.
        let old = std::mem::replace(&mut self.entries[index].state, State::Reserved);
        let State::Ready(payload) = old else { unreachable!("phase checked above"); };
        self.entries[index].state = State::CommitUnknown {
            replacement: payload,
            observed_revision: observation.history_revision,
        };
        let State::CommitUnknown { replacement, .. } = &self.entries[index].state else {
            unreachable!("fenced above");
        };
        let result = txn.compare_and_replace(CommitRequest {
            idempotency_key: id,
            source: &source,
            observed_revision: observation.history_revision,
            replacement,
        });
        match result {
            CommitResult::Committed(receipt) if receipt.history_revision > observation.history_revision => {
                self.entries.remove(index);
                Ok(AdoptOutcome::Adopted(receipt))
            }
            // An invalid receipt cannot prove whether a write happened.
            CommitResult::Committed(_) => Ok(AdoptOutcome::NeedsReconciliation),
            CommitResult::NotCommitted(HostRejection::Busy) => {
                let old = std::mem::replace(&mut self.entries[index].state, State::Reserved);
                let State::CommitUnknown { replacement, .. } = old else {
                    unreachable!("fenced above");
                };
                self.entries[index].state = State::Ready(replacement);
                Ok(AdoptOutcome::DeferredBusy)
            }
            CommitResult::NotCommitted(reason) => {
                self.entries.remove(index);
                Ok(AdoptOutcome::Discarded(DiscardReason::HostRejected(reason)))
            }
            CommitResult::Unknown => Ok(AdoptOutcome::NeedsReconciliation),
        }
    }

    /// Only host durable evidence may resolve a possibly committed transaction.
    /// This is not an ACK from a cancelled worker or a model assertion.
    pub fn reconcile(
        &mut self,
        id: CandidateId,
        evidence: Reconciliation,
    ) -> Result<ReconcileOutcome, Error> {
        let index = self.index(id)?;
        let observed_revision = match &self.entries[index].state {
            State::CommitUnknown { observed_revision, .. } => *observed_revision,
            _ => return Err(Error::WrongState),
        };
        match evidence {
            Reconciliation::Committed(receipt) if receipt.history_revision > observed_revision => {
                self.entries.remove(index);
                Ok(ReconcileOutcome::Adopted(receipt))
            }
            Reconciliation::Committed(_) => Ok(ReconcileOutcome::StillUnknown),
            Reconciliation::NotCommitted => {
                self.entries.remove(index);
                Ok(ReconcileOutcome::Discarded)
            }
            Reconciliation::StillUnknown => Ok(ReconcileOutcome::StillUnknown),
        }
    }

    /// Stops admission and discards ready/reserved candidates. Host must deliver
    /// all listed cancellation signals and keep ownership until is_empty().
    /// Repeated shutdown re-emits outstanding signals (bounded by four entries).
    /// Dropping this value does NOT abort or join external work.
    pub fn shutdown(&mut self) -> ShutdownReport {
        self.closed = true;
        let mut report = ShutdownReport::default();
        self.entries.retain_mut(|entry| match entry.state.phase() {
            Phase::Reserved | Phase::Ready => false,
            Phase::Preparing | Phase::CancelRequested(_) => {
                entry.state = State::CancelRequested(CancelReason::Shutdown);
                report.cancel_workers.push(entry.id);
                true
            }
            Phase::CommitUnknown => {
                report.reconcile_commits.push(entry.id);
                true
            }
        });
        report
    }
}
