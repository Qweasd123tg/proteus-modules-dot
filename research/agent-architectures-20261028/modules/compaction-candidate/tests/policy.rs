//! Source-only test cases for local review/execution by the user.
//! The fake host below is NOT a Core adapter or a cryptographic hash implementation.

use proteus_compaction_candidate::*;

fn source() -> SourceSnapshot {
    SourceSnapshot {
        session: SessionIdentity { session: [1; 16], incarnation: [2; 16] },
        context: ContextIdentity {
            provider: Digest([3; 32]),
            model: Digest([4; 32]),
            workflow: Digest([5; 32]),
            instructions: Digest([6; 32]),
            epochs: Epochs { history: 10, configuration: 20, policy: 30 },
        },
        prefix: PrefixIdentity {
            message_count: 2,
            first_message: [7; 16],
            last_message: [8; 16],
            digest: Digest([9; 32]),
        },
        history_revision: 40,
        snapshot_bytes: 80,
    }
}

fn observation() -> HostObservation {
    let s = source();
    HostObservation {
        session: s.session,
        context: s.context,
        prefix: Some(s.prefix),
        history_revision: s.history_revision,
        operations: Operations::default(),
    }
}

fn limits(count: usize) -> Limits {
    Limits {
        max_candidates: count,
        max_snapshot_bytes: 100,
        max_replacement_bytes: 20,
        max_reserved_bytes: count * 120,
    }
}

fn owner(count: usize) -> CandidateOwner {
    CandidateOwner::new(source().session, limits(count)).unwrap()
}

fn result() -> WorkerResult {
    WorkerResult::Completed(b"summary".to_vec().into_boxed_slice())
}

fn usage() -> Usage {
    Usage::Known { input_tokens: 100, output_tokens: 10 }
}

fn running(owner: &mut CandidateOwner) -> CandidateId {
    let id = owner.reserve(source()).unwrap();
    owner.mark_dispatched(id).unwrap();
    id
}

fn ready(owner: &mut CandidateOwner) -> CandidateId {
    let id = running(owner);
    assert_eq!(owner.finish(id, result(), usage(), &observation()), Ok(FinishOutcome::Ready));
    id
}

struct FakeTransaction {
    view: HostObservation,
    history: Vec<Vec<u8>>,
    observed: usize,
    commits: usize,
    unavailable: bool,
    panic_during_commit: bool,
    race_after_observation: bool,
    response: Option<CommitResult>,
    byte_budget: usize,
}

impl FakeTransaction {
    fn new() -> Self {
        Self {
            view: observation(),
            history: vec![b"old-1".to_vec(), b"old-2".to_vec()],
            observed: 0,
            commits: 0,
            unavailable: false,
            panic_during_commit: false,
            race_after_observation: false,
            response: None,
            byte_budget: 1000,
        }
    }
}

impl HostTransaction for FakeTransaction {
    fn observe(&mut self, _source: &SourceSnapshot) -> Result<HostObservation, ObservationError> {
        self.observed += 1;
        if self.unavailable {
            return Err(ObservationError::Unavailable);
        }
        Ok(self.view)
    }

    fn compare_and_replace(&mut self, request: CommitRequest<'_>) -> CommitResult {
        self.commits += 1;
        if self.panic_during_commit {
            panic!("simulated host panic after crossing the write boundary");
        }
        if let Some(response) = self.response {
            return response;
        }
        if self.race_after_observation {
            self.view.context.epochs.policy += 1;
            self.view.history_revision += 1;
        }
        // Even this fake rechecks at mutation; observation is not a CAS receipt.
        if compare_source(request.source, &self.view).is_err()
            || request.observed_revision != self.view.history_revision
        {
            return CommitResult::NotCommitted(HostRejection::CompareFailed);
        }
        if self.view.operations.execution_cancelled {
            return CommitResult::NotCommitted(HostRejection::Cancelled);
        }
        if self.view.operations.active_model_calls > 0
            || self.view.operations.active_tool_calls > 0
            || self.view.operations.model_stream_open
        {
            return CommitResult::NotCommitted(HostRejection::Busy);
        }
        let prefix_len = usize::try_from(request.source.prefix.message_count).unwrap();
        if prefix_len > self.history.len() {
            return CommitResult::NotCommitted(HostRejection::CompareFailed);
        }
        let suffix = self.history[prefix_len..].to_vec();
        let composed_bytes = request.replacement.len() + suffix.iter().map(Vec::len).sum::<usize>();
        // Bytes are only a test metric. Production must render/tokenize with the
        // actual provider and account for instructions, tools, anchors and suffix.
        if composed_bytes > self.byte_budget {
            return CommitResult::NotCommitted(HostRejection::OverBudget);
        }
        self.history = vec![request.replacement.to_vec()];
        self.history.extend(suffix);
        self.view.history_revision += 1;
        self.view.context.epochs.history += 1;
        CommitResult::Committed(CommitReceipt {
            history_revision: self.view.history_revision,
            retained_suffix_messages: (self.history.len() - 1) as u64,
        })
    }
}

#[test]
fn reservation_does_not_start_work_or_produce_a_ready_candidate() {
    let mut owner = owner(1);
    let id = owner.reserve(source()).unwrap();
    assert_eq!(owner.phase(id), Ok(Phase::Reserved));
    assert_eq!(owner.reserved_bytes(), 100);
    assert_eq!(owner.finish(id, result(), usage(), &observation()), Err(Error::WrongState));
    assert_eq!(owner.usage().settled_jobs, 0);
    let mut txn = FakeTransaction::new();
    assert_eq!(owner.try_adopt(id, &mut txn), Err(Error::WrongState));
    assert_eq!(txn.observed, 0);
}

#[test]
fn cancelled_worker_holds_capacity_until_settlement_and_late_callbacks_are_isolated() {
    let mut owner = owner(1);
    let first = running(&mut owner);
    assert_eq!(owner.cancel(first, CancelReason::User), Ok(CancelAction::SignalWorker));
    assert_eq!(owner.cancel(first, CancelReason::User), Ok(CancelAction::AlreadyRequested));
    assert_eq!(owner.reserve(source()), Err(Error::Capacity));
    assert_eq!(owner.reserved_bytes(), 100);
    assert_eq!(owner.finish(first, result(), usage(), &observation()),
        Ok(FinishOutcome::Discarded(DiscardReason::Cancelled(CancelReason::User))));
    let second = running(&mut owner);
    assert_ne!(first, second);
    assert_eq!(owner.finish(first, result(), usage(), &observation()), Err(Error::UnknownCandidate));
    assert_eq!(owner.phase(second), Ok(Phase::Preparing));
    assert_eq!(owner.usage().input_tokens, 100);
    assert_eq!(owner.usage().settled_jobs, 1);
}

#[test]
fn undispatched_cancel_releases_without_claiming_provider_usage() {
    let mut owner = owner(1);
    let id = owner.reserve(source()).unwrap();
    assert_eq!(owner.cancel(id, CancelReason::Expired), Ok(CancelAction::Discarded));
    assert!(owner.is_empty());
    assert_eq!(owner.usage(), UsageTotals::default());
    assert_eq!(owner.mark_dispatched(id), Err(Error::UnknownCandidate));
}

#[test]
fn append_only_tail_is_preserved_when_prefix_is_adopted() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    assert_eq!(owner.reserved_bytes(), b"summary".len());
    let mut txn = FakeTransaction::new();
    txn.history.push(b"new-user-turn".to_vec());
    txn.history.push(b"new-tool-result".to_vec());
    txn.view.history_revision += 2;
    assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::Adopted(CommitReceipt {
        history_revision: 43,
        retained_suffix_messages: 2,
    })));
    assert_eq!(txn.history, vec![b"summary".to_vec(), b"new-user-turn".to_vec(), b"new-tool-result".to_vec()]);
    assert!(owner.is_empty());
    assert_eq!(owner.reserved_bytes(), 0);
    assert_eq!(owner.usage().settled_jobs, 1);
}

#[test]
fn all_identity_axes_and_prefix_content_are_checked() {
    let s = source();
    let cases: Vec<(HostObservation, StaleReason)> = vec![
        (HostObservation { session: SessionIdentity { session: [44; 16], ..s.session }, ..observation() }, StaleReason::Session),
        (HostObservation { session: SessionIdentity { incarnation: [44; 16], ..s.session }, ..observation() }, StaleReason::Session),
        (HostObservation { context: ContextIdentity { provider: Digest([44; 32]), ..s.context }, ..observation() }, StaleReason::Provider),
        (HostObservation { context: ContextIdentity { model: Digest([44; 32]), ..s.context }, ..observation() }, StaleReason::Model),
        (HostObservation { context: ContextIdentity { workflow: Digest([44; 32]), ..s.context }, ..observation() }, StaleReason::Workflow),
        (HostObservation { context: ContextIdentity { instructions: Digest([44; 32]), ..s.context }, ..observation() }, StaleReason::Instructions),
        (HostObservation { context: ContextIdentity { epochs: Epochs { history: 11, ..s.context.epochs }, ..s.context }, ..observation() }, StaleReason::HistoryEpoch),
        (HostObservation { context: ContextIdentity { epochs: Epochs { configuration: 21, ..s.context.epochs }, ..s.context }, ..observation() }, StaleReason::ConfigurationEpoch),
        (HostObservation { context: ContextIdentity { epochs: Epochs { policy: 31, ..s.context.epochs }, ..s.context }, ..observation() }, StaleReason::PolicyEpoch),
        (HostObservation { history_revision: 39, ..observation() }, StaleReason::RevisionRegressed),
        (HostObservation { prefix: None, ..observation() }, StaleReason::Prefix),
        (HostObservation { prefix: Some(PrefixIdentity { digest: Digest([44; 32]), ..s.prefix }), ..observation() }, StaleReason::Prefix),
        (HostObservation { prefix: Some(PrefixIdentity { first_message: [44; 16], ..s.prefix }), ..observation() }, StaleReason::Prefix),
        (HostObservation { prefix: Some(PrefixIdentity { last_message: [44; 16], ..s.prefix }), ..observation() }, StaleReason::Prefix),
        (HostObservation { prefix: Some(PrefixIdentity { message_count: 1, ..s.prefix }), ..observation() }, StaleReason::Prefix),
    ];
    for (view, expected) in cases {
        assert_eq!(compare_source(&s, &view), Err(expected));
    }
    assert_eq!(compare_source(&s, &HostObservation { history_revision: 400, ..observation() }), Ok(()));
}

#[test]
fn stale_result_is_discarded_on_arrival_but_its_usage_is_kept() {
    let mut owner = owner(1);
    let id = running(&mut owner);
    let mut view = observation();
    view.context.epochs.configuration += 1;
    assert_eq!(owner.finish(id, result(), usage(), &view),
        Ok(FinishOutcome::Discarded(DiscardReason::Stale(StaleReason::ConfigurationEpoch))));
    assert!(owner.is_empty());
    assert_eq!(owner.usage().output_tokens, 10);
}

#[test]
fn ready_result_is_rechecked_at_adoption_and_cannot_overwrite_a_new_prefix() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.view.prefix = None;
    let before = txn.history.clone();
    assert_eq!(owner.try_adopt(id, &mut txn),
        Ok(AdoptOutcome::Discarded(DiscardReason::Stale(StaleReason::Prefix))));
    assert_eq!(txn.commits, 0);
    assert_eq!(txn.history, before);
}

#[test]
fn every_busy_operation_blocks_adoption_without_discarding_ready_data() {
    let busy = [
        Operations { active_model_calls: 1, ..Operations::default() },
        Operations { active_tool_calls: 1, ..Operations::default() },
        Operations { model_stream_open: true, ..Operations::default() },
    ];
    for operations in busy {
        let mut owner = owner(1);
        let id = running(&mut owner);
        let mut current = observation();
        current.operations = operations;
        assert_eq!(owner.finish(id, result(), usage(), &current), Ok(FinishOutcome::Ready));
        let mut txn = FakeTransaction::new();
        txn.view.operations = operations;
        assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::DeferredBusy));
        assert_eq!(owner.phase(id), Ok(Phase::Ready));
        assert_eq!(txn.commits, 0);
        txn.view.operations = Operations::default();
        assert!(matches!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::Adopted(_))));
    }
}

#[test]
fn cancellation_of_execution_is_checked_on_arrival_and_again_at_adoption() {
    let mut owner = owner(1);
    let id = running(&mut owner);
    let mut view = observation();
    view.operations.execution_cancelled = true;
    assert_eq!(owner.finish(id, result(), usage(), &view),
        Ok(FinishOutcome::Discarded(DiscardReason::ExecutionCancelled)));
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.view.operations.execution_cancelled = true;
    assert_eq!(owner.try_adopt(id, &mut txn),
        Ok(AdoptOutcome::Discarded(DiscardReason::ExecutionCancelled)));
    assert_eq!(txn.commits, 0);
}

#[test]
fn invalid_and_failed_results_have_explicit_outcomes_and_accounting() {
    let cases = vec![
        (WorkerResult::Completed(Vec::new().into_boxed_slice()), DiscardReason::EmptyReplacement),
        (WorkerResult::Completed(vec![1; 21].into_boxed_slice()), DiscardReason::ReplacementTooLarge),
        (WorkerResult::Failed, DiscardReason::Failed),
        (WorkerResult::Cancelled, DiscardReason::WorkerCancelled),
    ];
    let mut owner = owner(1);
    for (result, expected) in cases {
        let id = running(&mut owner);
        assert_eq!(owner.finish(id, result, Usage::Unknown, &observation()), Ok(FinishOutcome::Discarded(expected)));
        assert!(owner.is_empty());
    }
    assert_eq!(owner.usage().settled_jobs, 4);
    assert_eq!(owner.usage().unknown_usage_jobs, 4);
    assert_eq!(owner.usage().input_tokens, 0);
}

#[test]
fn duplicate_terminal_on_ready_entry_does_not_account_twice() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    assert_eq!(owner.finish(id, result(), usage(), &observation()), Err(Error::WrongState));
    assert_eq!(owner.usage().settled_jobs, 1);
    assert_eq!(owner.cancel(id, CancelReason::Superseded), Ok(CancelAction::Discarded));
    assert_eq!(owner.reserved_bytes(), 0);
    assert_eq!(owner.usage().settled_jobs, 1);
}

#[test]
fn aggregate_byte_reservation_is_independent_of_slot_count() {
    let mut configured = limits(4);
    configured.max_reserved_bytes = 150;
    let mut owner = CandidateOwner::new(source().session, configured).unwrap();
    let id = running(&mut owner);
    assert_eq!(owner.reserve(source()), Err(Error::ByteCapacity));
    assert_eq!(owner.finish(id, result(), usage(), &observation()), Ok(FinishOutcome::Ready));
    owner.reserve(source()).unwrap();
    assert_eq!(owner.reserved_bytes(), 107);
}

#[test]
fn invalid_limits_and_oversized_or_foreign_snapshots_are_rejected() {
    for count in [0, 5] {
        assert_eq!(CandidateOwner::new(source().session, limits(count)).unwrap_err(), Error::InvalidLimits);
    }
    let mut owner = owner(1);
    let mut s = source();
    s.snapshot_bytes = 101;
    assert_eq!(owner.reserve(s), Err(Error::SnapshotTooLarge));
    s = source();
    s.prefix.message_count = 0;
    assert_eq!(owner.reserve(s), Err(Error::InvalidSnapshot));
    s = source();
    s.session.incarnation = [55; 16];
    assert_eq!(owner.reserve(s), Err(Error::ForeignSession));
}

#[test]
fn unknown_commit_is_fenced_until_durable_reconciliation_and_not_retried() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.response = Some(CommitResult::Unknown);
    assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::NeedsReconciliation));
    assert_eq!(owner.phase(id), Ok(Phase::CommitUnknown));
    assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::NeedsReconciliation));
    assert_eq!(txn.commits, 1);
    assert_eq!(owner.cancel(id, CancelReason::User), Ok(CancelAction::ReconcileCommit));
    assert_eq!(owner.reserve(source()), Err(Error::Capacity));
    assert_eq!(owner.reconcile(id, Reconciliation::StillUnknown), Ok(ReconcileOutcome::StillUnknown));
    assert_eq!(owner.reconcile(id, Reconciliation::Committed(CommitReceipt {
        history_revision: 40,
        retained_suffix_messages: 0,
    })), Ok(ReconcileOutcome::StillUnknown));
    assert_eq!(owner.reconcile(id, Reconciliation::NotCommitted), Ok(ReconcileOutcome::Discarded));
    assert!(owner.is_empty());
}

#[test]
fn host_panic_crossing_commit_boundary_leaves_non_retryable_fence() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.panic_during_commit = true;
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| owner.try_adopt(id, &mut txn)));
    assert!(outcome.is_err());
    assert_eq!(owner.phase(id), Ok(Phase::CommitUnknown));
    assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::NeedsReconciliation));
    assert_eq!(txn.commits, 1);
}

#[test]
fn non_advancing_commit_receipt_remains_uncertain() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.response = Some(CommitResult::Committed(CommitReceipt {
        history_revision: 40,
        retained_suffix_messages: 0,
    }));
    assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::NeedsReconciliation));
    assert_eq!(owner.phase(id), Ok(Phase::CommitUnknown));
}

#[test]
fn host_final_cas_rejects_an_observation_to_write_race() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.race_after_observation = true;
    let before = txn.history.clone();
    assert_eq!(owner.try_adopt(id, &mut txn),
        Ok(AdoptOutcome::Discarded(DiscardReason::HostRejected(HostRejection::CompareFailed))));
    assert_eq!(txn.history, before);
}

#[test]
fn host_budget_is_for_replacement_plus_current_suffix_not_old_snapshot() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.history.push(b"suffix-longer-than-budget".to_vec());
    txn.view.history_revision += 1;
    txn.byte_budget = 20;
    let before = txn.history.clone();
    assert_eq!(owner.try_adopt(id, &mut txn),
        Ok(AdoptOutcome::Discarded(DiscardReason::HostRejected(HostRejection::OverBudget))));
    assert_eq!(txn.history, before);
    assert_eq!(owner.usage().input_tokens, 100);
}

#[test]
fn unavailable_observation_and_busy_commit_can_be_reconsidered_without_relaunch() {
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.unavailable = true;
    assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::DeferredObservationUnavailable));
    assert_eq!(txn.commits, 0);
    txn.unavailable = false;
    txn.response = Some(CommitResult::NotCommitted(HostRejection::Busy));
    assert_eq!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::DeferredBusy));
    assert_eq!(owner.phase(id), Ok(Phase::Ready));
    txn.response = None;
    assert!(matches!(owner.try_adopt(id, &mut txn), Ok(AdoptOutcome::Adopted(_))));
    assert_eq!(owner.usage().settled_jobs, 1);
}

#[test]
fn shutdown_keeps_running_and_uncertain_work_owned_until_settlement() {
    let mut owner = owner(4);
    let reserved = owner.reserve(source()).unwrap();
    let pending = running(&mut owner);
    let ready_id = ready(&mut owner);
    let uncertain = ready(&mut owner);
    let mut txn = FakeTransaction::new();
    txn.response = Some(CommitResult::Unknown);
    owner.try_adopt(uncertain, &mut txn).unwrap();
    let report = owner.shutdown();
    assert_eq!(report.cancel_workers, vec![pending]);
    assert_eq!(report.reconcile_commits, vec![uncertain]);
    assert_eq!(owner.phase(reserved), Err(Error::UnknownCandidate));
    assert_eq!(owner.phase(ready_id), Err(Error::UnknownCandidate));
    assert_eq!(owner.reserve(source()), Err(Error::Closed));
    assert!(!owner.is_empty());
    assert_eq!(owner.shutdown(), report);
    assert_eq!(owner.finish(pending, result(), usage(), &observation()),
        Ok(FinishOutcome::Discarded(DiscardReason::Cancelled(CancelReason::Shutdown))));
    assert_eq!(owner.reconcile(uncertain, Reconciliation::Committed(CommitReceipt {
        history_revision: 41,
        retained_suffix_messages: 0,
    })), Ok(ReconcileOutcome::Adopted(CommitReceipt {
        history_revision: 41,
        retained_suffix_messages: 0,
    })));
    assert!(owner.is_closed());
    assert!(owner.is_empty());
}

#[test]
fn foreign_incarnation_callback_cannot_settle_another_owner() {
    let mut first = owner(1);
    let old = running(&mut first);
    let mut s = source();
    s.session.incarnation = [55; 16];
    let mut second = CandidateOwner::new(s.session, limits(1)).unwrap();
    let current = second.reserve(s).unwrap();
    second.mark_dispatched(current).unwrap();
    assert_eq!(old.sequence(), current.sequence());
    assert_ne!(old, current);
    assert_eq!(second.finish(old, result(), usage(), &observation()), Err(Error::UnknownCandidate));
    assert_eq!(second.phase(current), Ok(Phase::Preparing));
    assert_eq!(second.usage().settled_jobs, 0);
}

#[test]
fn debug_never_prints_replacement_or_retained_anchor_bytes() {
    assert_eq!(format!("{:?}", result()), "Completed { replacement_bytes: 7 }");
    let mut owner = owner(1);
    let id = ready(&mut owner);
    let ready_debug = format!("{:?}", owner);
    assert!(ready_debug.contains("candidate_count: 1"));
    assert!(!ready_debug.contains("summary"));
    assert!(!ready_debug.contains("[115, 117, 109"));
    let mut txn = FakeTransaction::new();
    txn.response = Some(CommitResult::Unknown);
    owner.try_adopt(id, &mut txn).unwrap();
    let uncertain_debug = format!("{:?}", owner);
    assert!(!uncertain_debug.contains("summary"));
    assert!(!uncertain_debug.contains("[115, 117, 109"));
}
