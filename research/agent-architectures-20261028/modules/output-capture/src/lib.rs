//! Source-side artifact capture, before ToolResult/RPC construction.
//!
//! This prototype neither executes commands nor opens files. The existing
//! bounded preview collector is injected; its head/tail policy is not duplicated.
//! Only a trusted host may construct a sink, its grant, scope and artifact ID.
//! These Rust types are not an authentication mechanism or a wire protocol.

use std::io::{self, Read};

/// Fixed-size opaque host identity, never a filesystem path or model capability.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct HostId(pub [u8; 16]);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OutputStream {
    Stdout,
    Stderr,
    /// Host-observed ordering; does not claim source ordering between two pipes.
    Merged,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CaptureScope {
    pub session: HostId,
    pub invocation: HostId,
    pub capture: HostId,
    pub stream: OutputStream,
}

/// Reports saturation instead of quietly presenting an inexact count as exact.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct ByteCount {
    pub value: u64,
    pub saturated: bool,
}

impl ByteCount {
    fn add(&mut self, bytes: usize) {
        match u64::try_from(bytes).ok().and_then(|n| self.value.checked_add(n)) {
            Some(total) => self.value = total,
            None => {
                self.value = u64::MAX;
                self.saturated = true;
            }
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Interruption {
    Cancellation,
    Deadline,
    HostStopped,
}

/// EOF must come from the reader, not from observing that the process exited.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SourceEnd {
    Eof,
    Interrupted(Interruption),
    ReadFailed,
    Unknown,
}

/// Observation of the ORIGINAL command, supplied independently by the host.
/// A cancellation request alone must not be reported as confirmed termination.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CommandOutcome {
    NotStarted,
    Running,
    Exited { code: i32 },
    Terminated { signal: Option<u32> },
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SinkFailureKind {
    Io,
    QuotaExceeded,
    Cancelled,
    ProtocolViolation,
    Unknown,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FailureStage {
    Append,
    Seal,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CaptureFailure {
    pub stage: FailureStage,
    pub kind: SinkFailureKind,
}

/// A trusted host must reserve this budget against its session/global quota
/// BEFORE creating the sink. This library enforces only the per-capture ceiling.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SinkGrant {
    pub scope: CaptureScope,
    pub reserved_bytes: u64,
}

/// An append failure can have a partial or uncertain effect. There is no retry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AppendOutcome {
    /// The entire slice was accepted, in order. Durability awaits seal().
    Appended,
    Failed {
        kind: SinkFailureKind,
        /// Some(n): exactly this prefix was accepted and the remainder was not.
        /// None: effect unknown; up to the entire attempted slice may exist.
        confirmed_prefix: Option<usize>,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SealMetadata {
    pub scope: CaptureScope,
    pub source_end: SourceEnd,
    pub observed_bytes: ByteCount,
    pub appended_bytes: u64,
    pub cap_bytes: u64,
}

/// A sink returns this only after its publication/durability contract succeeds.
/// Reading still requires host-side ownership checks and bounded range access.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PublishedArtifact {
    pub scope: CaptureScope,
    pub artifact_id: HostId,
    /// Exclusive end of the confirmed readable range [0, readable_bytes).
    pub readable_bytes: u64,
}

/// Capability supplied by trusted host code, NEVER selected by model input.
///
/// Contract:
/// - grant() is immutable; append() accepts only this scoped stream, in order;
/// - implementations must not write more than the offered bytes or their quota;
/// - append() success means the complete slice, not an undocumented short write;
/// - seal() publishes only that exact prefix and must honor the supplied metadata;
/// - after an error the object is dropped, not retried, sealed, reopened or replayed;
/// - Drop must not retry writes or publish a failed capture. Quarantine/retention
///   of partial files is the host's responsibility, not this library's;
/// - latency/cancellation, file permissions, symlink-safe creation, redaction,
///   tenant ownership and global quotas are host obligations.
///
/// There is intentionally no blanket impl for std::io::Write and no path API.
pub trait TrustedArtifactSink: Send {
    fn grant(&self) -> SinkGrant;
    fn append(&mut self, bytes: &[u8]) -> AppendOutcome;
    fn seal(
        self: Box<Self>,
        metadata: SealMetadata,
    ) -> Result<PublishedArtifact, SinkFailureKind>;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ArtifactStatus {
    Disabled,
    /// Every OBSERVED byte is in the published artifact. Check source_end too.
    Captured,
    /// A confirmed prefix was published; additional observed bytes exceeded cap.
    Truncated,
    /// No readable reference is exposed, even if partial bytes may exist in storage.
    Failed,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CaptureReceipt {
    pub scope: CaptureScope,
    pub source_end: SourceEnd,
    pub status: ArtifactStatus,
    pub observed_bytes: ByteCount,
    /// Successful append acknowledgements, NOT a durability assertion on failure.
    pub confirmed_appended_bytes: u64,
    /// Upper bound for the last uncertain append; no later append is attempted.
    pub unconfirmed_append_bytes: u64,
    pub cap_bytes: Option<u64>,
    /// Confirmed appends reached cap. Alone this proves neither loss nor completeness.
    pub cap_reached: bool,
    pub artifact: Option<PublishedArtifact>,
    pub failure: Option<CaptureFailure>,
}

impl CaptureReceipt {
    /// A complete stream artifact requires both observed EOF and successful seal.
    /// This says nothing about the command's exit code or other output streams.
    pub fn is_complete_stream_artifact(&self) -> bool {
        self.source_end == SourceEnd::Eof && self.status == ArtifactStatus::Captured
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CaptureResult {
    pub command: CommandOutcome,
    pub capture: CaptureReceipt,
}

/// Returning the sink preserves host ownership on constructor rejection.
pub struct ScopeMismatch {
    pub expected: CaptureScope,
    pub actual: CaptureScope,
    pub sink: Box<dyn TrustedArtifactSink>,
}

enum SinkState {
    Disabled,
    Active(Box<dyn TrustedArtifactSink>),
    Failed(CaptureFailure),
}

/// One capture lifetime per stream. finish() consumes it to prevent reuse.
/// No output bytes, command strings, paths or error strings are retained here.
pub struct StreamCapture {
    scope: CaptureScope,
    cap: Option<u64>,
    observed: ByteCount,
    appended: u64,
    uncertain: u64,
    sink: SinkState,
}

impl StreamCapture {
    pub fn preview_only(scope: CaptureScope) -> Self {
        Self {
            scope,
            cap: None,
            observed: ByteCount::default(),
            appended: 0,
            uncertain: 0,
            sink: SinkState::Disabled,
        }
    }

    /// requested_cap is trusted configuration, not a model-provided disk budget.
    /// A host may impose a smaller cap than the reservation, never a larger one.
    pub fn with_artifact(
        scope: CaptureScope,
        requested_cap: u64,
        sink: Box<dyn TrustedArtifactSink>,
    ) -> Result<Self, ScopeMismatch> {
        let grant = sink.grant();
        if grant.scope != scope {
            return Err(ScopeMismatch {
                expected: scope,
                actual: grant.scope,
                sink,
            });
        }
        let mut capture = Self::preview_only(scope);
        capture.cap = Some(requested_cap.min(grant.reserved_bytes));
        capture.sink = SinkState::Active(sink);
        Ok(capture)
    }

    /// Call directly from the reader before constructing any full ToolResult.
    /// Borrowed input is not copied/retained. Continue draining after cap/failure.
    /// The supplied slice should itself come from a bounded host read buffer.
    pub fn observe(&mut self, bytes: &[u8]) {
        self.observed.add(bytes.len());
        // A caught host-sink panic must not silently turn an enabled capture
        // into Disabled or allow another append. No panic recovery is performed.
        let state = std::mem::replace(
            &mut self.sink,
            SinkState::Failed(CaptureFailure {
                stage: FailureStage::Append,
                kind: SinkFailureKind::Unknown,
            }),
        );
        self.sink = match state {
            SinkState::Active(mut sink) => {
                // Active is constructed only with a cap; no model can add a sink.
                let remaining = self.cap.unwrap_or(0).saturating_sub(self.appended);
                let offered = bytes.len().min(usize::try_from(remaining).unwrap_or(usize::MAX));
                if offered == 0 {
                    SinkState::Active(sink)
                } else {
                    // offered <= remaining <= u64::MAX, including wide-usize targets.
                    let offered_u64 = offered as u64;
                    self.uncertain = offered_u64;
                    match sink.append(&bytes[..offered]) {
                        AppendOutcome::Appended => {
                            self.uncertain = 0;
                            self.appended += offered_u64;
                            SinkState::Active(sink)
                        }
                        AppendOutcome::Failed { kind, confirmed_prefix } => {
                            let failure_kind = match confirmed_prefix {
                                Some(n) if n <= offered => {
                                    self.uncertain = 0;
                                    self.appended += n as u64;
                                    kind
                                }
                                Some(_) => {
                                    // Malformed acknowledgement: do not trust its count.
                                    self.uncertain = offered_u64;
                                    SinkFailureKind::ProtocolViolation
                                }
                                None => {
                                    self.uncertain = offered_u64;
                                    kind
                                }
                            };
                            // Drop, never seal/retry. No external command is replayed.
                            SinkState::Failed(CaptureFailure {
                                stage: FailureStage::Append,
                                kind: failure_kind,
                            })
                        }
                    }
                }
            }
            other => other,
        };
    }

    /// EOF / reader interruption and command outcome are independent host facts.
    /// Sink failure changes only capture metadata, never the original outcome.
    pub fn finish(self, source_end: SourceEnd, command: CommandOutcome) -> CaptureResult {
        let mut receipt = CaptureReceipt {
            scope: self.scope,
            source_end,
            status: ArtifactStatus::Disabled,
            observed_bytes: self.observed,
            confirmed_appended_bytes: self.appended,
            unconfirmed_append_bytes: self.uncertain,
            cap_bytes: self.cap,
            cap_reached: self.cap.map(|cap| self.appended == cap).unwrap_or(false),
            artifact: None,
            failure: None,
        };
        match self.sink {
            SinkState::Disabled => {}
            SinkState::Failed(failure) => {
                receipt.status = ArtifactStatus::Failed;
                receipt.failure = Some(failure);
            }
            SinkState::Active(sink) => {
                let metadata = SealMetadata {
                    scope: self.scope,
                    source_end,
                    observed_bytes: self.observed,
                    appended_bytes: self.appended,
                    cap_bytes: self.cap.unwrap_or(0),
                };
                match sink.seal(metadata) {
                    Ok(artifact)
                        if artifact.scope == self.scope
                            && artifact.readable_bytes == self.appended =>
                    {
                        receipt.status = if self.observed.saturated
                            || self.observed.value > self.appended
                        {
                            ArtifactStatus::Truncated
                        } else {
                            ArtifactStatus::Captured
                        };
                        receipt.artifact = Some(artifact);
                    }
                    other => {
                        receipt.status = ArtifactStatus::Failed;
                        receipt.failure = Some(CaptureFailure {
                            stage: FailureStage::Seal,
                            kind: match other {
                                Ok(_) => SinkFailureKind::ProtocolViolation,
                                Err(kind) => kind,
                            },
                        });
                    }
                }
            }
        }
        CaptureResult { command, capture: receipt }
    }
}

pub const READ_CHUNK_BYTES: usize = 16 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReadStep {
    Chunk { bytes: usize },
    Eof,
}

/// One bounded read step, not a command runner or a process lifecycle loop.
///
/// The host owns scratch and feeds its EXISTING bounded preview collector via
/// on_preview. Neither this adapter nor StreamCapture allocate the output text.
/// Cap exhaustion / append failure are deliberately not read errors: the host
/// must keep draining. Reader errors, including WouldBlock/Interrupted, return
/// unchanged for explicit host handling; no automatic IO or command retry.
///
/// Read may block: production integration needs existing async/nonblocking
/// readers plus host cancellation/deadlines. This helper does not implement them.
/// Drain both pipes concurrently; sequential stdout-then-stderr can deadlock.
pub fn read_step<R: Read, P: FnMut(&[u8])>(
    reader: &mut R,
    scratch: &mut [u8; READ_CHUNK_BYTES],
    capture: &mut StreamCapture,
    mut on_preview: P,
) -> io::Result<ReadStep> {
    let bytes = reader.read(scratch)?;
    if bytes == 0 {
        return Ok(ReadStep::Eof);
    }
    capture.observe(&scratch[..bytes]);
    on_preview(&scratch[..bytes]);
    Ok(ReadStep::Chunk { bytes })
}
