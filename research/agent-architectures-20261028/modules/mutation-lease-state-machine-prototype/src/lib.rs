//! Pure, single-owner mutation admission/lifetime prototype; no I/O or executor.
//!
//! Only a trusted workspace owner may drive this API. An ID is not authority.
//! The coordinator, not a requester future or returned handle, owns every lease.
//! See README.md for required host identity, settlement, and process boundaries.

use std::collections::BTreeMap;

/// Fixed prototype limits; terminal records count until explicitly forgotten.
pub const MAX_RECORDS: usize = 256;
pub const MAX_RESOURCES_PER_FOOTPRINT: usize = 128;
pub const MAX_OWNER_IDENTITY_BYTES: usize = 1024;
pub const MAX_RESOURCE_KEY_BYTES: usize = 1024;

/// Opaque, host-resolved identity, NOT an unchecked model-provided path.
pub type ResourceKey = String;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MutationFootprint {
    Resources(Vec<ResourceKey>),
    WorkspaceExclusive,
}

impl MutationFootprint {
    fn normalized(self) -> Result<Self, Error> {
        match self {
            Self::Resources(mut keys) => {
                // Bound the supplied count before sorting/deduplication, not just
                // the eventual distinct count. Caller allocation is outside this cap.
                if keys.len() > MAX_RESOURCES_PER_FOOTPRINT {
                    return Err(Error::Capacity {
                        limit: Capacity::ResourcesPerFootprint,
                        maximum: MAX_RESOURCES_PER_FOOTPRINT,
                    });
                }
                if let Some(key_index) = keys.iter().position(|key| key.len() > MAX_RESOURCE_KEY_BYTES) {
                    return Err(Error::InvalidFootprint { key_index, maximum_key_bytes: MAX_RESOURCE_KEY_BYTES });
                }
                // Empty/unknown mutation footprint is conservative, never no-op.
                if keys.is_empty() || keys.iter().any(|key| key.is_empty()) {
                    return Ok(Self::WorkspaceExclusive);
                }
                keys.sort();
                keys.dedup();
                // Do not retain oversized backing capacities from caller Vec/String.
                let bounded_keys = keys.iter().map(|key| key.as_str().to_owned()).collect();
                Ok(Self::Resources(bounded_keys))
            }
            Self::WorkspaceExclusive => Ok(Self::WorkspaceExclusive),
        }
    }

    fn conflicts(&self, other: &Self) -> bool {
        match (self, other) {
            (Self::Resources(left), Self::Resources(right)) => {
                left.iter().any(|key| right.binary_search(key).is_ok())
            }
            _ => true,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InvocationId {
    workspace: String,
    owner_incarnation: String,
    sequence: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Nesting {
    TopLevel,
    /// Derived by the host from lineage, never selected by the model.
    Nested,
}

/// Host assertions, not evidence that this library independently verifies.
/// Neither ToolResult, cancel ACK, elapsed time, nor requester drop is a variant.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SettlementEvidence {
    /// Owner proves dispatch never started; valid only for a reserved lease.
    NeverDispatched,
    /// All effects/delegates finished, and this invocation can initiate no more.
    EffectsQuiescent,
    /// Entire effect-capable tree exited; no detached or remote writer remains.
    EffectTreeExited,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Queued,
    Reserved,
    Dispatched,
    /// Retains original resources AND blocks new workspace mutation starts.
    Unknown,
    Settled(SettlementEvidence),
    CanceledBeforeAdmission,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LeaseRecord {
    /// Audit/binding field, deliberately NOT part of the conflict namespace.
    pub configuration_epoch: u64,
    pub footprint: MutationFootprint,
    pub phase: Phase,
    pub requester_gone: bool,
}

#[must_use]
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Admission {
    Acquired,
    BlockedBy(InvocationId),
}

#[must_use]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Departure {
    CanceledBeforeAdmission,
    LeaseRetained,
    AlreadyTerminal,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Capacity {
    Records,
    ResourcesPerFootprint,
    OwnerIdentityBytes,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Error {
    Capacity { limit: Capacity, maximum: usize },
    InvalidFootprint { key_index: usize, maximum_key_bytes: usize },
    InvalidOwnerIdentity,
    WrongOwner,
    UnknownInvocation,
    SequenceExhausted,
    NestedAcquisitionUnsupported,
    InvalidTransition { action: &'static str, phase: Phase },
    RequesterGone,
    WorkspaceQuarantined(InvocationId),
}

/// One non-cloneable coordinator for one actual workspace ownership domain.
/// No timer, automatic retry, auto-release, persistence, mutex, or IPC is supplied.
pub struct Coordinator {
    workspace: String,
    owner_incarnation: String,
    next_sequence: u64,
    records: BTreeMap<u64, LeaseRecord>,
}

impl Coordinator {
    /// The host must provide a unique incarnation, including across restarts.
    /// Constructing another coordinator does NOT coordinate with this one.
    pub fn new(workspace: String, owner_incarnation: String) -> Result<Self, Error> {
        if workspace.is_empty() || owner_incarnation.is_empty() {
            return Err(Error::InvalidOwnerIdentity);
        }
        if workspace.len() > MAX_OWNER_IDENTITY_BYTES || owner_incarnation.len() > MAX_OWNER_IDENTITY_BYTES {
            return Err(Error::Capacity { limit: Capacity::OwnerIdentityBytes, maximum: MAX_OWNER_IDENTITY_BYTES });
        }
        // Rebuild bounded strings instead of retaining arbitrary caller capacity.
        Ok(Self {
            workspace: workspace.as_str().to_owned(),
            owner_incarnation: owner_incarnation.as_str().to_owned(),
            next_sequence: 1,
            records: BTreeMap::new(),
        })
    }

    /// Call only after final before-tool transformations and policy/approval.
    /// Host binds the returned ID to that immutable effective call and its epoch.
    pub fn enqueue(
        &mut self,
        configuration_epoch: u64,
        footprint: MutationFootprint,
        nesting: Nesting,
    ) -> Result<InvocationId, Error> {
        if nesting == Nesting::Nested {
            return Err(Error::NestedAcquisitionUnsupported);
        }
        if self.records.len() >= MAX_RECORDS {
            return Err(Error::Capacity { limit: Capacity::Records, maximum: MAX_RECORDS });
        }
        let footprint = footprint.normalized()?;
        let sequence = self.next_sequence;
        self.next_sequence = sequence.checked_add(1).ok_or(Error::SequenceExhausted)?;
        self.records.insert(sequence, LeaseRecord {
            configuration_epoch,
            footprint,
            phase: Phase::Queued,
            requester_gone: false,
        });
        Ok(self.id(sequence))
    }

    /// Atomically reserves the complete sorted set, or reserves nothing.
    /// Earlier conflicting waiters cannot be overtaken; disjoint ones can.
    /// Host must revalidate resource identity before this and protect it to use.
    pub fn try_admit(&mut self, id: &InvocationId) -> Result<Admission, Error> {
        let sequence = self.sequence(id)?;
        let candidate = self.status(id)?;
        if candidate.phase != Phase::Queued {
            return Err(Error::InvalidTransition { action: "admit", phase: candidate.phase });
        }
        for (&other_sequence, other) in &self.records {
            if other_sequence == sequence { continue; }
            let blocks = match other.phase {
                Phase::Unknown => true,
                Phase::Reserved | Phase::Dispatched => other.footprint.conflicts(&candidate.footprint),
                Phase::Queued => other_sequence < sequence && other.footprint.conflicts(&candidate.footprint),
                Phase::Settled(_) | Phase::CanceledBeforeAdmission => false,
            };
            if blocks { return Ok(Admission::BlockedBy(self.id(other_sequence))); }
        }
        self.records.get_mut(&sequence).expect("checked record").phase = Phase::Reserved;
        Ok(Admission::Acquired)
    }

    /// Record dispatch BEFORE initiating any effect or sending to a worker.
    /// A failed/ambiguous send after this point still needs trusted settlement.
    pub fn mark_dispatched(&mut self, id: &InvocationId) -> Result<(), Error> {
        let sequence = self.sequence(id)?;
        let record = self.status(id)?;
        if record.phase != Phase::Reserved {
            return Err(Error::InvalidTransition { action: "dispatch", phase: record.phase });
        }
        if record.requester_gone { return Err(Error::RequesterGone); }
        // A different invocation may have become unknown after this reservation.
        if let Some((&blocked_by, _)) = self.records.iter().find(|(_, r)| r.phase == Phase::Unknown) {
            return Err(Error::WorkspaceQuarantined(self.id(blocked_by)));
        }
        self.records.get_mut(&sequence).expect("checked record").phase = Phase::Dispatched;
        Ok(())
    }

    /// Optional timeout/cancel/drop notification. Omitting it cannot release a lease.
    /// The host forwards cancellation separately; this method does not execute it.
    pub fn requester_departed(&mut self, id: &InvocationId) -> Result<Departure, Error> {
        let sequence = self.sequence(id)?;
        let record = self.records.get_mut(&sequence).ok_or(Error::UnknownInvocation)?;
        record.requester_gone = true;
        Ok(match record.phase {
            Phase::Queued => {
                record.phase = Phase::CanceledBeforeAdmission;
                Departure::CanceledBeforeAdmission
            }
            Phase::Reserved | Phase::Dispatched | Phase::Unknown => Departure::LeaseRetained,
            Phase::Settled(_) | Phase::CanceledBeforeAdmission => Departure::AlreadyTerminal,
        })
    }

    /// Unknown result, lost worker supervision, or uncertain physical settlement.
    /// Existing dispatched work may drain; new admissions AND dispatches stop.
    pub fn report_unknown(&mut self, id: &InvocationId) -> Result<(), Error> {
        let sequence = self.sequence(id)?;
        let record = self.records.get_mut(&sequence).ok_or(Error::UnknownInvocation)?;
        match record.phase {
            Phase::Dispatched | Phase::Unknown => { record.phase = Phase::Unknown; Ok(()) }
            phase => Err(Error::InvalidTransition { action: "report unknown", phase }),
        }
    }

    /// Only the trusted workspace/effect owner may call this with real evidence.
    /// Releases ordering protection, NOT a rollback or permission to replay effects.
    pub fn settle(&mut self, id: &InvocationId, evidence: SettlementEvidence) -> Result<(), Error> {
        let sequence = self.sequence(id)?;
        let record = self.records.get_mut(&sequence).ok_or(Error::UnknownInvocation)?;
        let valid = matches!(
            (record.phase, evidence),
            (Phase::Reserved, SettlementEvidence::NeverDispatched)
                | (Phase::Dispatched | Phase::Unknown, SettlementEvidence::EffectsQuiescent | SettlementEvidence::EffectTreeExited)
        );
        if !valid {
            return Err(Error::InvalidTransition { action: "settle", phase: record.phase });
        }
        record.phase = Phase::Settled(evidence);
        Ok(())
    }

    pub fn status(&self, id: &InvocationId) -> Result<&LeaseRecord, Error> {
        let sequence = self.sequence(id)?;
        self.records.get(&sequence).ok_or(Error::UnknownInvocation)
    }

    /// Optional bounded-history cleanup after host audit persistence, never active leases.
    /// IDs are not reused, so delayed callbacks cannot settle a newer invocation.
    pub fn forget_terminal(&mut self, id: &InvocationId) -> Result<(), Error> {
        let sequence = self.sequence(id)?;
        let phase = self.status(id)?.phase;
        if !matches!(phase, Phase::Settled(_) | Phase::CanceledBeforeAdmission) {
            return Err(Error::InvalidTransition { action: "forget", phase });
        }
        self.records.remove(&sequence);
        Ok(())
    }

    fn id(&self, sequence: u64) -> InvocationId {
        InvocationId { workspace: self.workspace.clone(), owner_incarnation: self.owner_incarnation.clone(), sequence }
    }

    fn sequence(&self, id: &InvocationId) -> Result<u64, Error> {
        if id.workspace != self.workspace || id.owner_incarnation != self.owner_incarnation {
            return Err(Error::WrongOwner);
        }
        Ok(id.sequence)
    }
}
