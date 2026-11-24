use super::*;
use crate as proteus_session_semantics;
use crate::{
    contracts::{ModelCallOrigin, OperationOwner, StorageConversation, SessionStorageRequest as Request,
        SessionStorageResponse as Response, StorageResumeState, StorageSnapshot, StorageRevision, SessionLocator},
    domain::{AgentOutput, AgentTask, new_exchange_id, new_execution_id, new_record_id, new_session_id,
        new_thread_id, new_turn_id, ModelRef, ReasoningConfig},
    journal::{JournalValidationState, ModelRequestRecorded, ModelResponseRecorded, TurnOpened, TurnSettled, JOURNAL_SCHEMA_VERSION},
    model_standard::{CanonicalMessage, CanonicalModelRequest, CanonicalModelResponse, FinishReason, MessageRole,
        ModelFailure, ModelFailureKind, TokenUsage},
};
use anyhow::{Result,bail,ensure};
use std::path::PathBuf;

#[derive(Clone)]
struct RemoteSessionStore {
    id: SessionId,
    prefix_matches: bool,
}
impl RemoteSessionStore {
    fn session_id(&self) -> SessionId { self.id }
    fn request(&self, request: Request) -> Result<Response> {
        assert!(matches!(request,Request::CompareSnapshots { .. }));
        Ok(Response::SnapshotPrefix { matches: self.prefix_matches })
    }
}
#[derive(Clone)]
struct RemoteJournalCursor { snapshot: StorageSnapshot }
impl RemoteJournalCursor { fn last_session_seq(&self)->u64 { self.snapshot.revision.session_seq } }
#[derive(Clone)]
struct RemoteJournalSnapshot {
    snapshot: StorageSnapshot,
    display_records: Option<Vec<u64>>,
    records: Vec<JournalRecord>,
    late_io_error: bool,
}
impl RemoteJournalSnapshot {
    fn scan(&mut self, mut visit: impl FnMut(JournalRecord)->Result<()>) -> Result<()> {
        for record in &self.records { visit(record.clone())?; }
        if self.late_io_error { bail!("fixture transport error after last record"); }
        Ok(())
    }
}
#[derive(Default)]
struct DisplayRecordWriter(Vec<u64>);
impl DisplayRecordWriter {
    fn push(&mut self, record: &JournalRecord) { self.0.push(record.session_seq); }
    fn finish(self)->Option<Vec<u64>> { Some(self.0) }
}
fn is_display_kind(kind: crate::journal::JournalKind) -> bool { kind.is_display_record() }
struct RemoteValidatedRead {
    source: RemoteJournalSnapshot,
    resume: StorageResumeState,
    prefix_history_fingerprints: Option<Vec<[u8;32]>>,
}

include!(concat!(env!("CARGO_MANIFEST_DIR"), "/../../routes.rs"));

fn fixture(n: usize, id: SessionId) -> (Vec<JournalRecord>, Vec<ModelUsageStatus>) {
    let thread = new_thread_id();
    let mut out = Vec::new();
    let mut statuses = Vec::new();
    for slot in 0..n {
        let turn = new_turn_id();
        let execution = new_execution_id();
        let exchange_id = new_exchange_id();
        let mut push = |entry, execution_id| out.push(JournalRecord {
            schema_version: JOURNAL_SCHEMA_VERSION, record_id: new_record_id(), session_seq: out.len() as u64 + 1,
            timestamp_ms: 100 + out.len() as i64, session_id: id, execution_id,
            thread_id: Some(thread), turn_id: Some(turn), entry,
        });
        push(JournalEntry::TurnOpened(TurnOpened {
            task: AgentTask::new("synthetic usage proof", PathBuf::from("/")),
            intent: None, base_history_revision: 0, module_epoch: 0, config_snapshot: serde_json::json!({}),
        }), Some(execution));
        let mut request = CanonicalModelRequest::new(
            ModelRef::new(format!("fixture-{slot}-{}", "🚀".repeat(24)), "model-".repeat(20)),
            vec![CanonicalMessage::text(MessageRole::User, "typed history fixture")],
        );
        request.reasoning = ReasoningConfig::new(Some(format!("effort-{slot}-{}", "λ".repeat(16))), false);
        request.limits.max_output_tokens = Some(160);
        push(JournalEntry::ModelRequestRecorded(ModelRequestRecorded {
            exchange_id, origin: ModelCallOrigin::Direct, owner: OperationOwner::Workflow, request,
        }), Some(execution));
        let kind = if slot + 1 == n { 4 } else { slot % 4 };
        let status = match kind {
            0 => {
                let response = CanonicalModelResponse::new(
                    CanonicalMessage::text(MessageRole::Assistant, "synthetic answer"), vec![], FinishReason::Stop,
                ).with_usage(TokenUsage::new(120, 30));
                push(JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
                    exchange_id, outcome: ModelResponseOutcome::Response { response },
                }), Some(execution));
                push(JournalEntry::TurnSettled(TurnSettled {
                    status: TurnSettlementStatus::Success, output: Some(AgentOutput::text("ok")), error: None,
                }), None);
                ModelUsageStatus::Completed
            },
            1 => {
                push(JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
                    exchange_id, outcome: ModelResponseOutcome::Error {
                        failure: ModelFailure::new(ModelFailureKind::Other, "fixture error"),
                    },
                }), Some(execution));
                push(JournalEntry::TurnSettled(TurnSettled {
                    status: TurnSettlementStatus::Error, output: None, error: Some("fixture error".into()),
                }), None);
                ModelUsageStatus::Error
            },
            2 | 3 => {
                push(JournalEntry::TurnSettled(TurnSettled {
                    status: if kind == 2 { TurnSettlementStatus::Canceled } else { TurnSettlementStatus::Timeout },
                    output: None, error: Some("stopped by fixture".into()),
                }), None);
                if kind == 2 { ModelUsageStatus::Canceled } else { ModelUsageStatus::Timeout }
            },
            _ => ModelUsageStatus::Unfinished,
        };
        statuses.push(status);
    }
    (out, statuses)
}

fn usage_of(id: SessionId, records: &[JournalRecord]) -> UsageProjection {
    let mut validation = JournalValidationState::default();
    let mut usage = UsageProjection::default();
    let mut seq = 1;
    for record in records {
        validation.apply_sequenced(id, record, &mut seq)
            .unwrap_or_else(|error| panic!("fixture sequence {}: {error}",record.session_seq));
        usage.apply(record);
    }
    usage
}

#[test]
fn independent_owned_usage_snapshot_bytes_and_capacity() {
    for count in [0,1,2,5,31,32,33,256,1025] {
        let id = new_session_id();
        let (records,statuses) = fixture(count,id);
        for mode in 0..3 {
            let mut usage = usage_of(id, &records);
            if mode == 1 { usage.requests.reserve(4096); }
            if mode == 2 { usage.requests = usage.requests.into_boxed_slice().into_vec(); }
            let array = usage.requests.as_ptr();
            let tight = usage.requests.capacity() == count;
            let moved_in: Vec<_> = usage.requests.iter().map(|x| (
                x.model.provider.as_ptr(), x.model.model.as_ptr(), x.reasoning_effort.as_ref().unwrap().as_ptr(),
            )).collect();
            let before = usage.snapshot(id);
            assert_eq!(before.requests.iter().map(|x| x.status).collect::<Vec<_>>(), statuses);
            let source_size = usage.requests.capacity();
            let after = usage.into_snapshot(id);
            let moved_out: Vec<_> = after.requests.iter().map(|x| (
                x.model.provider.as_ptr(), x.model.model.as_ptr(), x.reasoning_effort.as_ref().unwrap().as_ptr(),
            )).collect();
            assert_eq!(moved_in,moved_out,"all nested string owners survive even during compaction");
            assert!(before.requests.iter().zip(&after.requests).all(|(a,b)| a.model.provider.as_ptr()!=b.model.provider.as_ptr()));
            if tight && count!=0 { assert_eq!(after.requests.as_ptr(),array); }
            assert_eq!(after.requests.capacity(),count,"never retain geometric slack");
            assert_eq!(after,before);
            assert_eq!(serde_json::to_vec(&after).unwrap(),serde_json::to_vec(&before).unwrap());
            println!("OWNERS {count} {mode} {source_size} {}", after.requests.capacity());
        }
    }
}

#[test]
fn independent_exact_core_fold_body_and_late_errors() {
    for count in [0,1,5,33,257] {
        let id = new_session_id();
        let (records,statuses) = fixture(count,id);
        let store = RemoteSessionStore { id, prefix_matches: true };
        let snapshot = StorageSnapshot {
            session: SessionLocator {session_id:id,key:"synthetic".into()},
            snapshot_id: "fixture-head".into(), revision: StorageRevision {session_seq: records.len() as u64,history_revision:0},
            content_sha256:"a".repeat(64),
        };
        let source = RemoteJournalSnapshot { snapshot: snapshot.clone(), display_records:None, records, late_io_error:false };
        for with_previous in [false,true] {
            let previous = with_previous.then_some(RemoteJournalCursor { snapshot:snapshot.clone() });
            let old = RemoteValidatedRead::validate_before(store.clone(),source.clone(),previous.as_ref(),Some(DisplayRecordWriter::default())).unwrap();
            let new = RemoteValidatedRead::validate_after(store.clone(),source.clone(),previous.as_ref(),Some(DisplayRecordWriter::default())).unwrap();
            assert_eq!(old.1,new.1);
            assert_eq!(old.0.prefix_history_fingerprints,new.0.prefix_history_fingerprints);
            assert_eq!(old.0.source.display_records,new.0.source.display_records);
            assert_eq!(serde_json::to_vec(&old.0.resume).unwrap(),serde_json::to_vec(&new.0.resume).unwrap());
            assert_eq!(new.0.resume.usage.requests.iter().map(|r|r.status).collect::<Vec<_>>(),statuses);
        }
        for control in 0..3 {
            if control == 2 && count == 0 { continue; }
            let mut bad = source.clone();
            match control {
                0 => bad.late_io_error = true,
                1 => bad.snapshot.revision.history_revision = 1,
                _ => bad.records.last_mut().unwrap().session_seq += 1,
            }
            let old = RemoteValidatedRead::validate_before(store.clone(),bad.clone(),None,None).err().unwrap();
            let new = RemoteValidatedRead::validate_after(store.clone(),bad,None,None).err().unwrap();
            assert_eq!(old.to_string(),new.to_string());
        }
    }
}
