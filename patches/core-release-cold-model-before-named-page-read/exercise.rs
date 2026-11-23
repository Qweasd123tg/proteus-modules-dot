use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::{Cell, RefCell},
    hint::black_box,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(usize)]
enum Kind {
    History,
    PartVec,
    Text,
    Context,
    Hashes,
    Sets,
    Display,
}

#[derive(Clone, Debug)]
struct Watch {
    address: usize,
    kind: Kind,
    requested: Option<usize>,
    freed: bool,
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
struct Totals {
    watched: [usize; 7],
    freed: [usize; 7],
    bytes: [usize; 7],
    invalid: bool,
}
#[derive(Default)]
struct Probe {
    watches: Vec<Watch>,
    totals: Totals,
}
thread_local! {
    static ACTIVE: Cell<bool> = const { Cell::new(false) };
    static PROBE: RefCell<Probe> = RefCell::new(Probe::default());
}
fn add(w: &mut Vec<Watch>, address: usize, kind: Kind, requested: Option<usize>) {
    w.push(Watch {
        address,
        kind,
        requested,
        freed: false,
    });
}
fn add_vec<T>(w: &mut Vec<Watch>, v: &Vec<T>, kind: Kind) {
    let size = v.capacity() * std::mem::size_of::<T>();
    if size > 0 {
        add(w, v.as_ptr().addr(), kind, Some(size));
    }
}
fn arm(model: &SessionReadModel) {
    assert!(!ACTIVE.get());
    let mut watches = Vec::with_capacity(model.conversation.messages.len() * 2 + 13);
    add_vec(&mut watches, &model.conversation.messages, Kind::History);
    add_vec(
        &mut watches,
        &model.conversation.model_context,
        Kind::Context,
    );
    for m in &model.conversation.messages {
        add_vec(&mut watches, &m.parts, Kind::PartVec);
        for part in &m.parts {
            if let ContentPart::Text { text } = &part.payload {
                if text.capacity() > 0 {
                    add(
                        &mut watches,
                        text.as_ptr().addr(),
                        Kind::Text,
                        Some(text.capacity()),
                    );
                }
            }
        }
    }
    if let Some(pre) = &model.prefix {
        pre.observe_for_proof(&mut watches);
    }
    add_vec(&mut watches, &model.transcript, Kind::Display);
    for row in model.transcript.iter().take(3) {
        if row.text.capacity() > 0 {
            add(
                &mut watches,
                row.text.as_ptr().addr(),
                Kind::Display,
                Some(row.text.capacity()),
            );
        }
    }
    watches.sort_unstable_by_key(|w| w.address);
    assert!(watches.windows(2).all(|p| p[0].address < p[1].address));
    let mut totals = Totals::default();
    for w in &watches {
        totals.watched[w.kind as usize] += 1;
    }
    PROBE.with(|p| *p.borrow_mut() = Probe { watches, totals });
    ACTIVE.set(true);
}
fn access(p: *mut u8, l: Layout, deallocated: bool) {
    if !ACTIVE.try_with(Cell::get).unwrap_or(false) {
        return;
    }
    let lo = p.addr();
    let hi = lo.saturating_add(l.size());
    PROBE.with(|shared| {
        let mut probe = shared.borrow_mut();
        let Probe { watches, totals } = &mut *probe;
        let at = watches.partition_point(|w| w.address < lo);
        for w in watches[at..].iter_mut().take_while(|w| w.address < hi) {
            // An armed address identifies a live initial allocation; after its
            // first free, reused memory is a different generation, ignored here.
            if w.freed {
                continue;
            }
            if !deallocated
                || w.requested
                    .is_some_and(|s| s != l.size() || w.address != lo)
            {
                totals.invalid = true;
                continue;
            }
            w.freed = true;
            totals.freed[w.kind as usize] += 1;
            totals.bytes[w.kind as usize] += l.size();
        }
    });
}
#[inline(never)]
fn current() -> Totals {
    PROBE.with(|p| black_box(p.borrow().totals))
}
struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, l: Layout, n: usize) -> *mut u8 {
        access(ptr, l, false);
        unsafe { System.realloc(ptr, l, n) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, l: Layout) {
        access(ptr, l, true);
        unsafe { System.dealloc(ptr, l) }
    }
}
#[global_allocator]
static METER: Meter = Meter;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Save {
    Pass,
    FailEarly,
    FailHead,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Lookup {
    Pass,
    Missing,
    HeaderFault,
    BodyFault,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Fault {
    None,
    Render,
    Scan,
    Summary,
}
#[derive(Clone, Copy, Debug)]
struct Plan {
    label: &'static str,
    count: usize,
    paged: bool,
    save: Save,
    lookup: Lookup,
    fault: Fault,
    prior: bool,
}
impl Plan {
    fn named_available(self) -> bool {
        self.prior || self.save != Save::FailEarly
    }
    fn tail(self) -> bool {
        self.paged && self.named_available() && self.lookup == Lookup::Pass
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Step {
    Validate,
    Render,
    PrefixScan,
    Summary,
    SaveCall,
    SaveEarlyFault,
    WriteNamed,
    WriteHead,
    HeadFault,
    ReadNamed,
    ReadBody,
}
struct RemoteSessionStore {
    plan: Plan,
    steps: RefCell<Vec<Step>>,
    page: RefCell<Option<Vec<u8>>>,
    token: String,
    entry: Cell<Option<Totals>>,
    transcript_pointer: Cell<usize>,
}
impl RemoteSessionStore {
    fn note(&self, step: Step) {
        self.steps.borrow_mut().push(step);
    }
}
struct RemoteJournalSnapshot<'a> {
    records: Vec<u8>,
    rows: Vec<AppTranscriptMessage>,
    store: &'a RemoteSessionStore,
}
impl RemoteJournalSnapshot<'_> {
    fn scan_display(&mut self, consume: impl FnOnce(JournalRecord) -> Result<()>) -> Result<()> {
        self.store.note(Step::PrefixScan);
        let bytes = std::mem::take(&mut self.records);
        if !bytes.is_empty() {
            consume(serde_json::from_slice(&bytes)?)?;
        }
        if self.store.plan.fault == Fault::Scan {
            anyhow::bail!("strict scan error");
        }
        Ok(())
    }
}
struct ContextState(Vec<ModelContextObservation>);
impl ContextState {
    fn snapshot(self) -> Vec<ModelContextObservation> {
        self.0
    }
}
struct ResumeState {
    history: Vec<CanonicalMessage>,
    history_revision: u64,
    model_context: ContextState,
    usage: SessionUsageSnapshot,
}
struct RemoteValidatedRead<'a> {
    position: RemoteJournalCursor,
    snapshot: RemoteJournalSnapshot<'a>,
    state: ResumeState,
}
impl<'a> RemoteValidatedRead<'a> {
    fn cursor(&self) -> RemoteJournalCursor {
        self.position.clone()
    }
    fn into_parts(self) -> (RemoteJournalSnapshot<'a>, ResumeState) {
        (self.snapshot, self.state)
    }
}
mod cache {
    use super::*;
    pub(super) fn summary(
        store: &RemoteSessionStore,
        history: &[CanonicalMessage],
    ) -> Result<AppSessionSummary> {
        store.note(Step::Summary);
        if store.plan.fault == Fault::Summary {
            anyhow::bail!("summary error");
        }
        Ok(AppSessionSummary {
            session_dir: "/session-fixture".into(),
            session_id: id(1),
            parent_session_id: None,
            workspace_path: "/workspace-fixture".into(),
            message_count: history.len(),
            updated_at_ms: Some(183),
            preview: Some("fixture".into()),
            activity: None,
        })
    }
    pub(super) fn save_model(
        store: &RemoteSessionStore,
        source: &RemoteCacheSource,
        model: &SessionReadModel,
        cursor: Option<()>,
    ) -> Option<()> {
        assert!(cursor.is_none());
        assert_eq!(source.revision().as_deref(), Some(store.token.as_str()));
        assert_eq!(model.summary.message_count, store.plan.count);
        assert_eq!(model.conversation.revision, 27);
        assert_eq!(model.transcript.len(), store.plan.count);
        assert_eq!(
            model.prefix.as_ref().unwrap().history.len(),
            store.plan.count
        );
        store.note(Step::SaveCall);
        let result = (|| {
            if store.plan.save == Save::FailEarly {
                store.note(Step::SaveEarlyFault);
                return None;
            }
            store.note(Step::WriteNamed);
            let bytes = page_bytes(&model.transcript, &store.token, store.plan);
            *store.page.borrow_mut() = Some(bytes);
            store.note(Step::WriteHead);
            if store.plan.save == Save::FailHead {
                store.note(Step::HeadFault);
                return None;
            }
            Some(())
        })();
        store
            .transcript_pointer
            .set(model.transcript.as_ptr().addr());
        arm(model); // Exact save exit, after the adapter's staging scratch lifetime.
        result
    }
    pub(super) fn transcript_page(
        store: &RemoteSessionStore,
        before: Option<usize>,
        revision: Option<&str>,
        stale: bool,
    ) -> Option<AppTranscriptPage> {
        store.entry.set(Some(current())); // Before adapter logging or decoding.
        store.note(Step::ReadNamed);
        assert_eq!(revision, Some(store.token.as_str()));
        assert!(before.is_none() && !stale);
        if matches!(store.plan.lookup, Lookup::Missing | Lookup::HeaderFault) {
            return None;
        }
        let page = store.page.borrow();
        let data = page.as_ref()?;
        store.note(Step::ReadBody);
        if store.plan.lookup == Lookup::BodyFault {
            return None;
        }
        let p: AppTranscriptPage = serde_json::from_slice(data).ok()?;
        (Some(p.revision.as_str()) == revision).then_some(p)
    }
}

fn id(x: u128) -> Uuid {
    Uuid::from_u128(x)
}
fn position() -> RemoteJournalCursor {
    RemoteJournalCursor {
        snapshot: StorageSnapshot {
            session: SessionLocator {
                session_id: id(1),
                key: "fixed-fixture".to_owned(),
            },
            snapshot_id: "snapshot-handle".into(),
            revision: StorageRevision {
                session_seq: 3,
                history_revision: 27,
            },
            content_sha256: "0".repeat(64),
        },
    }
}
fn row(m: &CanonicalMessage, index: usize) -> AppTranscriptMessage {
    let ContentPart::Text { text } = &m.parts[0].payload else {
        unreachable!()
    };
    AppTranscriptMessage {
        message_id: Some(m.id),
        timestamp_ms: Some(index as i64),
        phase: m.phase,
        role: if index % 2 == 0 { "user" } else { "assistant" }.into(),
        text: text.clone(),
        images: vec![],
        tool: None,
        subagent: None,
        streaming: false,
    }
}
fn page_bytes(rows: &[AppTranscriptMessage], token: &str, plan: Plan) -> Vec<u8> {
    let start = rows.len().saturating_sub(PAGE_ROWS);
    serde_json::to_vec(&AppTranscriptPage {
        revision: token.to_owned(),
        start,
        total: rows.len(),
        messages: rows[start..].to_vec(),
        base: plan.prior.then(|| AppTranscriptBase {
            revision: "old-named".into(),
            common_prefix: 3,
        }),
    })
    .unwrap()
}
fn build(plan: Plan) -> (Vec<CanonicalMessage>, Vec<AppTranscriptMessage>, Vec<u8>) {
    let mut ms = Vec::with_capacity(plan.count);
    for i in 0..plan.count {
        let text = if plan.count == 50000 {
            format!("Fixture row {i}\n{}", SEED.repeat(4))
        } else {
            format!("Fixture {i}\n\u{2002}\0É𝄞 & \"quoted\"")
        };
        ms.push(CanonicalMessage {
            id: id(1000 + i as u128),
            role: if i % 2 == 0 {
                MessageRole::User
            } else {
                MessageRole::Assistant
            },
            phase: None,
            parts: vec![CanonicalPart {
                part_id: id(100000 + i as u128),
                provenance: if i % 2 == 0 {
                    PartProvenance::User
                } else {
                    PartProvenance::Model
                },
                scope: PartScope::Conversation,
                payload: ContentPart::Text { text },
            }],
            name: None,
            tool_call_id: None,
            metadata: Value::Null,
        });
    }
    if ms.is_empty() {
        return (ms, vec![], vec![]);
    }
    let rows = ms.iter().enumerate().map(|(i, m)| row(m, i)).collect();
    // Materialize one immutable JournalRecord, then decode independent exact typed
    // canonical owners from the same construction, as in separate staged/state DTOs.
    let canonical = serde_json::from_slice(&serde_json::to_vec(&ms).unwrap()).unwrap();
    let record = JournalRecord {
        schema_version: 21,
        session_id: id(1),
        record_id: id(17),
        session_seq: 1,
        timestamp_ms: 70,
        execution_id: None,
        thread_id: Some(id(8)),
        turn_id: None,
        entry: JournalEntry::HistoryMutated(HistoryMutated {
            previous_revision: 26,
            new_revision: 27,
            mutation: HistoryMutationKind::Append,
            messages: ms,
            compaction: None,
            tool_results: vec![],
        }),
    };
    (canonical, rows, serde_json::to_vec(&record).unwrap())
}
#[derive(Debug, PartialEq, Eq)]
struct ResultShape {
    steps: Vec<Step>,
    wire: Vec<u8>,
    entry: Option<Totals>,
    exit: Totals,
}
fn drive(plan: Plan, new: bool) -> ResultShape {
    assert!(!ACTIVE.get());
    PROBE.with(|p| *p.borrow_mut() = Probe::default());
    let pos = position();
    let token = RemoteCacheSource::from_cursor(&pos).revision().unwrap();
    let (history, rows, records) = build(plan);
    let seed_text: usize = history
        .iter()
        .map(|m| {
            let ContentPart::Text { text } = &m.parts[0].payload else {
                unreachable!()
            };
            text.len()
        })
        .sum();
    if plan.count == 50000 {
        assert_eq!(seed_text, 19688890);
    }
    let previous = plan.prior.then(|| page_bytes(&rows, &token, plan));
    let store = RemoteSessionStore {
        plan,
        steps: RefCell::new(vec![Step::Validate]),
        page: RefCell::new(previous),
        token,
        entry: Cell::new(None),
        transcript_pointer: Cell::new(0),
    };
    let read = RemoteValidatedRead {
        position: pos,
        snapshot: RemoteJournalSnapshot {
            records,
            rows,
            store: &store,
        },
        state: ResumeState {
            history,
            history_revision: 27,
            model_context: ContextState(if plan.count == 50000 {
                vec![]
            } else {
                vec![ModelContextObservation::Usage {
                    total_tokens: 101,
                    last_tokens: 46,
                }]
            }),
            usage: SessionUsageSnapshot {
                session_id: id(1),
                revision: 3,
                latest_turn_id: None,
                requests: vec![],
            },
        },
    };
    let render = |source: &mut RemoteJournalSnapshot| {
        store.note(Step::Render);
        if plan.fault == Fault::Render {
            anyhow::bail!("render error");
        }
        Ok(std::mem::take(&mut source.rows))
    };
    let view = if new {
        candidate::project(&store, read, plan.paged, render)
    } else {
        stock::project(&store, read, plan.paged, render)
    };
    let exit = current();
    ACTIVE.set(false);
    let wire = match view {
        Ok(v) => {
            assert_eq!(plan.fault, Fault::None);
            assert_eq!(v.summary.message_count, plan.count);
            assert_eq!(v.revision, 27);
            assert_eq!(v.usage.revision, 3);
            if plan.tail() {
                assert_eq!(v.transcript.len(), plan.count.min(50));
                let c = v.cursor.as_ref().unwrap();
                assert_eq!(c.before, plan.count.saturating_sub(50));
                assert_eq!(c.revision, store.token);
                assert_eq!(c.base.is_some(), plan.prior);
            } else {
                assert!(v.cursor.is_none());
                assert_eq!(v.transcript.len(), plan.count);
                assert_eq!(v.transcript.as_ptr().addr(), store.transcript_pointer.get());
            }
            serde_json::to_vec(&(v.summary, v.revision, v.usage, v.transcript, v.cursor)).unwrap()
        }
        Err(e) => {
            assert_ne!(plan.fault, Fault::None);
            serde_json::to_vec(&e.to_string()).unwrap()
        }
    };
    ResultShape {
        steps: store.steps.into_inner(),
        wire,
        entry: store.entry.get(),
        exit,
    }
}
fn steps(plan: Plan) -> Vec<Step> {
    use Step::*;
    let mut want = vec![Validate, Render];
    if plan.fault == Fault::Render {
        return want;
    }
    want.push(PrefixScan);
    if plan.fault == Fault::Scan {
        return want;
    }
    want.push(Summary);
    if plan.fault == Fault::Summary {
        return want;
    }
    want.push(SaveCall);
    if plan.save == Save::FailEarly {
        want.push(SaveEarlyFault);
    } else {
        want.extend([WriteNamed, WriteHead]);
        if plan.save == Save::FailHead {
            want.push(HeadFault);
        }
    }
    if plan.paged {
        want.push(ReadNamed);
        if plan.named_available() && !matches!(plan.lookup, Lookup::Missing | Lookup::HeaderFault) {
            want.push(ReadBody);
        }
    }
    want
}
fn compare(plan: Plan) {
    let s = drive(plan, false);
    let c = drive(plan, true);
    assert_eq!(s.steps, steps(plan), "stock {}", plan.label);
    assert_eq!(s.steps, c.steps, "trace {}", plan.label);
    assert!(s.wire == c.wire, "exact result bytes {}", plan.label);
    assert_eq!(s.exit, c.exit, "final outcome ownership {}", plan.label);
    let disp = Kind::Display as usize;
    assert!(!s.exit.invalid && !c.exit.invalid);
    for k in 0..disp {
        assert_eq!(s.exit.watched[k], s.exit.freed[k]);
    }
    assert_eq!(
        s.exit.freed[disp],
        if plan.tail() { s.exit.watched[disp] } else { 0 }
    );
    if plan.fault == Fault::None && plan.paged {
        let (a, b) = (s.entry.unwrap(), c.entry.unwrap());
        assert_eq!(a.watched, b.watched);
        assert_eq!(a.freed, [0; 7], "stock entry {}", plan.label);
        assert_eq!(a.bytes, [0; 7]);
        assert_eq!(b.freed[disp], 0, "fallback still alive");
        for k in 0..disp {
            assert_eq!(b.watched[k], b.freed[k], "candidate entry {}", plan.label);
            assert_eq!(
                b.bytes[k], c.exit.bytes[k],
                "all watched owner frees happen before lookup"
            );
        }
        assert!(!a.invalid && !b.invalid);
        if plan.count == 50000 {
            assert_eq!(b.freed, [1, 50000, 50000, 0, 1, 3, 0]);
            assert_eq!(b.bytes[Kind::Text as usize], 19688890);
            assert!(b.bytes[Kind::History as usize] > 0 && b.bytes[Kind::Sets as usize] > 2400000);
            println!(
                "LIVENESS {} {} {}",
                plan.label,
                serde_json::to_string(&a).unwrap(),
                serde_json::to_string(&b).unwrap()
            );
        }
    } else {
        assert!(s.entry.is_none() && c.entry.is_none());
    }
    let hash = ring::digest::digest(&ring::digest::SHA256, &s.wire);
    let hash: String = hash.as_ref().iter().map(|b| format!("{b:02x}")).collect();
    println!("CASE {} {} {}", plan.label, s.steps.len(), hash);
}
fn main() {
    let input = serde_json::from_str::<Value>(r#"{"z":1,"a":2}"#).unwrap();
    let keys: Vec<_> = input.as_object().unwrap().keys().collect();
    if cfg!(feature = "preserve_order") {
        assert_eq!(keys, vec!["z", "a"]);
    } else {
        assert_eq!(keys, vec!["a", "z"]);
    }
    println!("MODE preserve_order={}", cfg!(feature = "preserve_order"));
    let p = Plan {
        label: "cold-50000",
        count: 50000,
        paged: true,
        save: Save::Pass,
        lookup: Lookup::Pass,
        fault: Fault::None,
        prior: false,
    };
    compare(p);
    let p = Plan {
        count: 73,
        label: "small-normal",
        ..p
    };
    compare(p);
    for other in [
        Plan {
            label: "named-head-fault-old-head",
            save: Save::FailHead,
            prior: true,
            ..p
        },
        Plan {
            label: "early-save-fault-prior-named",
            save: Save::FailEarly,
            prior: true,
            ..p
        },
        Plan {
            label: "early-save-fault-no-named",
            save: Save::FailEarly,
            ..p
        },
        Plan {
            label: "successful-save-missing-index",
            lookup: Lookup::Missing,
            ..p
        },
        Plan {
            label: "successful-save-corrupt-header",
            lookup: Lookup::HeaderFault,
            ..p
        },
        Plan {
            label: "successful-save-corrupt-body",
            lookup: Lookup::BodyFault,
            ..p
        },
        Plan {
            label: "unpaged-original-fallback",
            paged: false,
            ..p
        },
        Plan {
            label: "strict-render-failure",
            fault: Fault::Render,
            ..p
        },
        Plan {
            label: "strict-scan-failure",
            fault: Fault::Scan,
            ..p
        },
        Plan {
            label: "summary-failure",
            fault: Fault::Summary,
            ..p
        },
        Plan {
            label: "zero-rows",
            count: 0,
            ..p
        },
    ] {
        compare(other);
    }
}
