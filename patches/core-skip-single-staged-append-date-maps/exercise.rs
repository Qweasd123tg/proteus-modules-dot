use ::std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::{Cell, RefCell},
    hint::black_box,
    rc::Rc,
};
use serde_json::json;
fn id(n: u128) -> Uuid {
    Uuid::from_u128(n)
}
fn part(n: u128, payload: ContentPart) -> CanonicalPart {
    CanonicalPart {
        part_id: id(1000000 + n),
        provenance: PartProvenance::Model,
        scope: PartScope::Conversation,
        payload,
    }
}
fn msg(n: u128, role: MessageRole, parts: Vec<CanonicalPart>) -> CanonicalMessage {
    CanonicalMessage {
        id: id(n),
        role,
        phase: None,
        parts,
        name: None,
        tool_call_id: None,
        metadata: Value::Null,
    }
}
fn tx(s: impl Into<String>) -> ContentPart {
    ContentPart::Text { text: s.into() }
}
fn single(n: u128, s: impl Into<String>) -> CanonicalMessage {
    msg(
        n,
        if n % 2 == 0 {
            MessageRole::User
        } else {
            MessageRole::Assistant
        },
        vec![part(n, tx(s))],
    )
}
fn rec(seq: u64, turn: Option<u128>, entry: JournalEntry) -> JournalRecord {
    JournalRecord {
        schema_version: SCHEMA,
        record_id: id(100000 + seq as u128),
        session_seq: seq,
        timestamp_ms: 1000 - seq as i64 * 7,
        session_id: id(99000),
        execution_id: None,
        thread_id: turn.map(|_| id(77)),
        turn_id: turn.map(id),
        entry,
    }
}
fn mutation(
    kind: HistoryMutationKind,
    messages: Vec<CanonicalMessage>,
    comp: bool,
) -> JournalEntry {
    JournalEntry::HistoryMutated(HistoryMutated {
        previous_revision: 0,
        new_revision: 1,
        mutation: kind,
        messages,
        compaction: comp.then(|| HistoryCompactionReport::unchanged(0, None)),
        tool_results: vec![],
    })
}
fn append(m: Vec<CanonicalMessage>) -> JournalEntry {
    mutation(HistoryMutationKind::Append, m, false)
}
fn open() -> JournalEntry {
    JournalEntry::TurnOpened(TurnOpened {
        task: AgentTask {
            text: "run".into(),
            cwd: "/tmp".into(),
        },
        intent: None,
        base_history_revision: 0,
        module_epoch: 0,
        config_snapshot: Value::Null,
    })
}
fn response(m: CanonicalMessage) -> JournalEntry {
    JournalEntry::ModelResponseRecorded(ModelResponseRecorded {
        exchange_id: id(622),
        outcome: ModelResponseOutcome::Response {
            response: CanonicalModelResponse {
                messages: vec![m],
                tool_calls: vec![],
                finish_reason: FinishReason::Stop,
                usage: None,
                end_turn: None,
                provider_metadata: Value::Null,
            },
        },
    })
}
fn settled(status: TurnSettlementStatus, error: Option<&str>) -> JournalEntry {
    JournalEntry::TurnSettled(TurnSettled {
        status,
        error: error.map(String::from),
        output: None,
    })
}
fn mixed() -> Vec<JournalRecord> {
    let mut hidden = single(1, "request");
    hidden.parts[0].scope = PartScope::Request;
    let mut trace = single(2, "trace");
    trace.parts[0].scope = PartScope::Trace;
    let blank = single(3, " \u{2002}\u{3000}\n");
    let hidden_later = single(1, "must remain hidden A");
    let trace_later = single(2, "must remain hidden B");
    let blank_later = single(3, "must remain hidden C");
    let mut live = single(90, "live only");
    live.parts[0].part_id = id(3232);
    let mut rehost = single(91, "  Дата 🌊\0 \u{2009}");
    rehost.parts[0].part_id = id(3232);
    rehost.phase = Some(MessagePhase::FinalAnswer);
    let call = ToolCall::new("c", "task", json!({"s":[1,2]}));
    let compound = msg(
        99,
        MessageRole::Assistant,
        vec![
            part(101, tx(" before ")),
            part(102, ContentPart::ToolCall { call: call.clone() }),
            part(103, tx("после")),
            part(104, tx("三")),
            part(
                105,
                ContentPart::Image {
                    image: ImageRef {
                        id: "i".into(),
                        name: "a".into(),
                        mime_type: "image/png".into(),
                        path: "i".into(),
                    },
                },
            ),
        ],
    );
    let reason = msg(
        91,
        MessageRole::Assistant,
        vec![part(
            106,
            ContentPart::ReasoningSummary {
                text: "earlier reasoning".into(),
            },
        )],
    );
    let result = msg(
        102,
        MessageRole::Tool,
        vec![part(
            107,
            ContentPart::ToolResult {
                result: ToolResult::ok("c".into(), "yes").with_metadata(json!({"x":true})),
            },
        )],
    );
    let opaque = msg(
        103,
        MessageRole::System,
        vec![part(
            108,
            ContentPart::Opaque {
                format: "private".into(),
                data: json!("unused"),
            },
        )],
    );
    let mut cp = single(25, "append compactor stays");
    cp.parts[0].provenance = PartProvenance::Compactor;
    let mut hp = single(26, "replace compactor hidden");
    hp.parts[0].provenance = PartProvenance::Compactor;
    let mut phase = single(110, "developer commentary");
    phase.role = MessageRole::Developer;
    phase.phase = Some(MessagePhase::Commentary);
    vec![
        rec(1, Some(7), open()),
        rec(2, Some(8), append(vec![live])),
        rec(
            3,
            None,
            append(vec![
                hidden,
                trace,
                blank,
                hidden_later,
                trace_later,
                blank_later,
                rehost,
                compound,
                opaque,
                msg(104, MessageRole::Tool, vec![]),
                phase,
            ]),
        ),
        rec(
            4,
            None,
            mutation(HistoryMutationKind::Append, vec![reason, result, cp], true),
        ),
        rec(
            5,
            None,
            mutation(
                HistoryMutationKind::Replace,
                vec![hp, single(27, "kept replace")],
                true,
            ),
        ),
        rec(
            6,
            None,
            mutation(
                HistoryMutationKind::Checkpoint,
                vec![single(40, "kept checkpoint")],
                false,
            ),
        ),
        rec(
            7,
            Some(7),
            settled(TurnSettlementStatus::Error, Some("  failed reason  ")),
        ),
        rec(8, Some(7), settled(TurnSettlementStatus::Timeout, None)),
        rec(9, Some(7), settled(TurnSettlementStatus::Success, None)),
    ]
}
fn next_id() -> Uuid {
    use std::sync::atomic::{AtomicUsize, Ordering};
    static SEQ: AtomicUsize = AtomicUsize::new(1_000_000_000);
    id(SEQ.fetch_add(1, Ordering::Relaxed) as u128)
}
#[derive(Clone, Serialize)]
#[serde(tag = "operation", rename_all = "snake_case")]
enum Request {
    OpenSnapshot {
        session: SessionLocator,
    },
    OpenDisplaySnapshot {
        session: SessionLocator,
    },
    ReadRecords {
        snapshot: StorageSnapshot,
        after_seq: u64,
        limit: u32,
    },
    ReadDisplayRecords {
        snapshot: StorageSnapshot,
        after_seq: u64,
        limit: u32,
    },
}
#[derive(Clone)]
struct ResumeState;
struct DisplayProjection {
    snapshot: StorageSnapshot,
    state: ResumeState,
}
enum Response {
    Snapshot {
        snapshot: StorageSnapshot,
    },
    DisplaySnapshot {
        projection: Option<DisplayProjection>,
    },
    Records {
        page: StorageRecordPage,
    },
}
#[derive(Clone)]
struct RemoteSessionStore {
    descriptor: Descriptor,
    service: FixtureService,
    records: Rc<Vec<JournalRecord>>,
    log: Rc<RefCell<Vec<&'static str>>>,
    snapshot: StorageSnapshot,
}
#[derive(Clone)]
struct Descriptor {
    session: SessionLocator,
}
#[derive(Clone)]
struct FixtureService(&'static str);
impl FixtureService {
    fn supports_display_projection(&self) -> bool {
        self.0 != "unsupported" && self.0 != "direct"
    }
}
impl RemoteSessionStore {
    fn new(records: &[JournalRecord], route: &str) -> Self {
        let session = SessionLocator {
            session_id: id(99000),
            key: "fixture journal".into(),
        };
        let snapshot = StorageSnapshot {
            session: session.clone(),
            snapshot_id: "fixed prefix".into(),
            content_sha256: "a".repeat(64),
            revision: StorageRevision {
                session_seq: records.last().map_or(0, |r| r.session_seq),
                history_revision: 1,
            },
        };
        Self {
            descriptor: Descriptor { session },
            service: FixtureService(match route {
                "projected" => "projected",
                "fallback" => "fallback",
                "unsupported" => "unsupported",
                "direct" => "direct",
                _ => unreachable!(),
            }),
            records: Rc::new(records.to_vec()),
            log: Rc::new(RefCell::new(Vec::with_capacity(32))),
            snapshot,
        }
    }
    fn request(&self, r: Request) -> Result<Response> {
        let tag = match r {
            Request::OpenSnapshot { ref session } => {
                assert_eq!(session, &self.snapshot.session);
                "OpenSnapshot"
            }
            Request::OpenDisplaySnapshot { ref session } => {
                assert_eq!(session, &self.snapshot.session);
                "OpenDisplaySnapshot"
            }
            Request::ReadRecords {
                ref snapshot,
                limit,
                ..
            } => {
                assert_eq!(snapshot, &self.snapshot);
                assert_eq!(limit, 64);
                "ReadRecords"
            }
            Request::ReadDisplayRecords {
                ref snapshot,
                limit,
                ..
            } => {
                assert_eq!(snapshot, &self.snapshot);
                assert_eq!(limit, 64);
                "ReadDisplayRecords"
            }
        };
        self.log.borrow_mut().push(tag);
        Ok(match r {
            Request::OpenSnapshot { .. } => Response::Snapshot {
                snapshot: self.snapshot.clone(),
            },
            Request::OpenDisplaySnapshot { .. } => Response::DisplaySnapshot {
                projection: (self.service.0 == "projected").then(|| DisplayProjection {
                    snapshot: self.snapshot.clone(),
                    state: ResumeState,
                }),
            },
            Request::ReadRecords { after_seq, .. }
            | Request::ReadDisplayRecords { after_seq, .. } => {
                let display = tag == "ReadDisplayRecords";
                let mut it = self.records.iter().filter(|r| {
                    r.session_seq > after_seq && (!display || r.entry.kind().is_display_record())
                });
                let records: Vec<_> = it.by_ref().take(64).cloned().collect();
                let next_after_seq = it.next().map(|_| records.last().unwrap().session_seq);
                Response::Records {
                    page: StorageRecordPage {
                        snapshot: self.snapshot.clone(),
                        records,
                        next_after_seq,
                    },
                }
            }
        })
    }
}
#[derive(Clone, Copy, Debug, Default)]
struct MeterStats {
    live: usize,
    peak: usize,
    requested: usize,
    allocs: usize,
    reallocs: usize,
    checkpoints: [usize; 3],
}
thread_local! {
 static METER:Cell<Option<MeterStats>>=const{Cell::new(None)};
 static OBSERVE:Cell<bool>=const{Cell::new(false)};
 static HIT:Cell<usize>=const{Cell::new(0)};
 static VISITS:Cell<usize>=const{Cell::new(0)};
}
fn hit() {
    if OBSERVE.get() {
        HIT.set(HIT.get() + 1)
    }
}
fn live_checkpoint(n: usize) {
    if OBSERVE.get() && n == 0 {
        VISITS.set(VISITS.get() + 1)
    }
    METER.with(|x| {
        if let Some(mut s) = x.get() {
            s.checkpoints[n] = s.live;
            x.set(Some(s));
        }
    });
}
fn note(old: usize, new: usize, a: bool, r: bool) {
    let _ = METER.try_with(|x| {
        if let Some(mut s) = x.get() {
            s.live = s.live.checked_sub(old).unwrap() + new;
            s.peak = s.peak.max(s.live);
            s.requested += new;
            s.allocs += usize::from(a);
            s.reallocs += usize::from(r);
            x.set(Some(s))
        }
    });
}
struct Meter;
#[global_allocator]
static ALLOC: Meter = Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc(l) };
        if !p.is_null() {
            note(0, l.size(), true, false)
        }
        p
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        let p = unsafe { System.alloc_zeroed(l) };
        if !p.is_null() {
            note(0, l.size(), true, false)
        }
        p
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            note(l.size(), n, false, true)
        }
        q
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        note(l.size(), 0, false, false);
        unsafe { System.dealloc(p, l) }
    }
}
fn reset() {
    OBSERVE.set(true);
    HIT.set(0);
    VISITS.set(0)
}
fn load<R>(f: impl FnOnce() -> R) -> (R, usize, usize) {
    reset();
    let r = f();
    OBSERVE.set(false);
    (r, HIT.get(), VISITS.get())
}
fn wire<T: Serialize + ?Sized>(v: &T) -> Vec<u8> {
    serde_json::to_vec(v).unwrap()
}
fn hash(v: &[u8]) -> String {
    ring::digest::digest(&ring::digest::SHA256, v)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
fn seeded(n: usize) -> Vec<JournalRecord> {
    let mut r = rec(1, None, append(published_seed_messages(n, 4)));
    r.thread_id = Some(id(77));
    vec![r]
}
fn case(
    label: &str,
    r: &[JournalRecord],
    route: &str,
    live: Option<TurnId>,
    hit_expected: bool,
    err: Option<(&str, usize)>,
    want: impl Fn(&[AppTranscriptMessage]),
) {
    let mut traces = Vec::new();
    let extra = rec(
        2,
        None,
        append(vec![single(999, "unexpected appended spool entry")]),
    );
    macro_rules! check {
        ($arm:ident,$optimized:expr) => {{
            let mut s = $arm::prep(r, route);
            if err.is_some() {
                s.corrupt(label, &extra);
            }
            let (out, hits, visits) = load(|| s.run(live));
            assert_eq!(hits, usize::from($optimized && hit_expected), "{label}");
            let output = if let Some((needle, count)) = err {
                let e = out.unwrap_err().to_string();
                assert!(e.contains(needle), "{label}: {e}");
                assert_eq!(visits, count, "{label}");
                wire(&e)
            } else {
                let rows = out.unwrap();
                want(&rows);
                let expected = match route {
                    "projected" => vec!["OpenDisplaySnapshot", "ReadDisplayRecords"],
                    "fallback" => vec!["OpenDisplaySnapshot", "OpenSnapshot", "ReadRecords"],
                    "unsupported" => vec!["OpenSnapshot", "ReadRecords"],
                    "direct" => {
                        assert!(
                            s.ops()
                                .iter()
                                .all(|op| matches!(*op, "OpenSnapshot" | "ReadRecords"))
                        );
                        s.ops()
                    }
                    _ => unreachable!(),
                };
                assert_eq!(s.ops(), expected, "{label} operations");
                wire(&rows)
            };
            traces.push((output, s.ops(), visits, s.size()));
        }};
    }
    check!(stock, false);
    check!(candidate, true);
    check!(baseline, false);
    check!(composed, true);
    assert!(traces.windows(2).all(|x| x[0] == x[1]), "parity: {label}");
    println!("{label}/{route}: {}", hash(&wire(&traces[0])));
}
fn semantics() {
    for n in [5000, 50000] {
        let records = seeded(n);
        let JournalEntry::HistoryMutated(m) = &records[0].entry else {
            unreachable!()
        };
        let size = wire(&records[0]).len();
        assert!(size < 65 * 1024 * 1024 && wire(&m.messages).len() < 32 * 1024 * 1024);
        println!(
            "single-{n}: typed-record-bytes={size}, canonical-messages-bytes={}",
            wire(&m.messages).len()
        );
        for route in ["projected", "fallback", "unsupported"] {
            case(
                &format!("single-{n}"),
                &records,
                route,
                None,
                true,
                None,
                |rows| {
                    assert_eq!(rows.len(), n);
                    for (row, m) in rows.iter().zip(&m.messages) {
                        assert_eq!(row.timestamp_ms, Some(records[0].timestamp_ms));
                        assert_eq!(row.message_id, Some(m.id));
                        let ContentPart::Text { text } = &m.parts[0].payload else {
                            panic!()
                        };
                        assert_eq!(&row.text, text);
                    }
                },
            );
        }
    }
    let mut a = single(1, " Лёд 🦀\0 ");
    let mut b = single(2, "B");
    a.parts.push(part(99, tx("more")));
    b.id = a.id;
    b.parts[0].part_id = a.parts[0].part_id;
    let mut hide = single(3, "omit");
    hide.parts[0].scope = PartScope::Request;
    let mut repeat = single(4, "still omitted");
    repeat.parts[0].part_id = hide.parts[0].part_id;
    let many = vec![
        a,
        b,
        hide,
        repeat,
        single(5, " \u{2002} "),
        msg(6, MessageRole::User, vec![]),
    ];
    for date in [i64::MIN, i64::MAX] {
        let mut r = rec(1, Some(7), append(many.clone()));
        r.timestamp_ms = date;
        case(
            "single-duplicates-extremes",
            &[r.clone()],
            "projected",
            None,
            true,
            None,
            |rows| {
                assert_eq!(rows.len(), 1);
                assert_eq!(rows[0].text, " Лёд 🦀\0 \nmore");
                assert_eq!(rows[0].timestamp_ms, Some(date));
            },
        );
        case(
            "single-live-skipped",
            &[r],
            "projected",
            Some(id(7)),
            true,
            None,
            |rows| assert!(rows.is_empty()),
        );
    }
    for (label, route, r) in [
        ("direct-single", "direct", seeded(4)),
        ("empty-stage", "fallback", vec![]),
        (
            "hard-reset",
            "projected",
            vec![rec(
                1,
                None,
                mutation(
                    HistoryMutationKind::Replace,
                    vec![single(1, "replacement")],
                    false,
                ),
            )],
        ),
        (
            "append-with-compaction",
            "projected",
            vec![rec(
                1,
                None,
                mutation(HistoryMutationKind::Append, vec![single(1, "append")], true),
            )],
        ),
        (
            "singleton-mixed",
            "projected",
            vec![rec(
                1,
                None,
                append(vec![msg(
                    1,
                    MessageRole::Assistant,
                    vec![
                        part(1, tx("plain")),
                        part(
                            2,
                            ContentPart::ReasoningSummary {
                                text: "not plain".into(),
                            },
                        ),
                    ],
                )]),
            )],
        ),
        ("multi-date-rehost-mixed", "projected", mixed()),
    ] {
        case(label, &r, route, None, false, None, |_| {});
    }
    let m = single(4, "model response then append");
    case(
        "staged-model-commit",
        &[
            rec(1, Some(7), open()),
            rec(2, Some(7), response(m.clone())),
            rec(3, Some(7), append(vec![m])),
        ],
        "projected",
        None,
        false,
        None,
        |rows| assert_eq!(rows[0].timestamp_ms, Some(986)),
    );
    let r = seeded(3);
    for (label, needle, count, hit) in [
        ("short", "transcript staging record count changed", 0, false),
        (
            "wrong-count",
            "transcript staging record count changed",
            1,
            false,
        ),
        ("non-lf", "incomplete transcript staging record", 1, true),
        ("parse", "expected value", 1, true),
        ("extra", "transcript staging record count changed", 2, true),
    ] {
        case(
            label,
            &r,
            "projected",
            None,
            hit,
            Some((needle, count)),
            |_| panic!("can't publish error"),
        )
    }
    macro_rules! failures {
        ($arm:ident) => {{
            let mut s = $arm::prep(&r, "projected");
            s.fail_read();
            let (res, hits, visits) = load(|| s.run(None));
            assert_eq!(
                res.unwrap_err()
                    .downcast_ref::<std::io::Error>()
                    .unwrap()
                    .raw_os_error(),
                Some(9)
            );
            assert_eq!((hits, visits), (0, 0));
            let mut s = $arm::prep(&r, "projected");
            s.corrupt("non-lf", &r[0]);
            assert_eq!(s.callback_fails(), "injected callback failure");
            let mut s = $arm::prep(&r, "projected");
            s.zero_seq(&r[0]);
            let e =
                std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| s.run(None))).unwrap_err();
            assert_eq!(
                e.downcast_ref::<&str>()
                    .copied()
                    .or_else(|| e.downcast_ref::<String>().map(String::as_str)),
                Some("validated journal sequences start at one")
            );
        }};
    }
    failures!(stock);
    failures!(candidate);
    failures!(baseline);
    failures!(composed);
    println!(
        "early-read errno=9; callback error takes precedence over malformed tail; zero sequence panic in every arm"
    );
    println!("SEMANTICS PASS");
}
fn allocation() {
    for n in [5000, 50000] {
        let r = seeded(n);
        for route in ["projected", "fallback"] {
            let mut vals = Vec::new();
            let mut bytes = None;
            macro_rules! scan {
                ($arm:ident) => {{
                    let mut stage = $arm::prep(&r, route);
                    let size = stage.size();
                    METER.set(Some(MeterStats::default()));
                    let rows = black_box(stage.run(None).unwrap());
                    let before_drop = METER.get().unwrap();
                    assert!(before_drop.live > 0);
                    assert_eq!(rows.len(), n);
                    METER.set(None);
                    let w = wire(&rows);
                    if let Some(want) = &bytes {
                        assert_eq!(&w, want)
                    } else {
                        bytes = Some(w);
                    }
                    METER.set(Some(before_drop));
                    drop(rows);
                    assert_eq!(METER.replace(None).unwrap().live, 0);
                    vals.push((size, before_drop));
                }};
            }
            scan!(stock);
            scan!(candidate);
            scan!(baseline);
            scan!(composed);
            assert!(bytes.is_some());
            for (s, t) in [(0, 1), (2, 3)] {
                let a = vals[s].1;
                let b = vals[t].1;
                assert_eq!(vals[s].0, vals[t].0);
                assert_eq!(a.live, b.live);
                assert!(a.checkpoints[1] >= b.checkpoints[1] + n * 64);
                assert!(a.peak >= b.peak);
                assert!(a.requested > b.requested && a.allocs > b.allocs);
            }
            println!("{n}/{route}: {vals:?}");
        }
    }
    println!("ALLOCATION PASS");
}
#[repr(C)]
struct Ts {
    i: i64,
    n: i64,
}
unsafe extern "C" {
    fn clock_gettime(clockid: i32, t: *mut Ts) -> i32;
}
fn cpu_ns() -> u64 {
    let mut t = Ts { i: 0, n: 0 };
    assert_eq!(unsafe { clock_gettime(2, &mut t) }, 0);
    t.i as u64 * 1_000_000_000 + t.n as u64
}
fn cpu() {
    // Predeclared scoped guard, not an app startup claim. Alternating AB/CD vs DC/BA
    // order; guard paired medians + 90th percentiles. Small/control reps >10 ms typical.
    const MEDIAN_LIMIT: f64 = 1.12;
    const P90_LIMIT: f64 = 1.25;
    for (label, r, pairs, reps) in [
        ("single-small", seeded(16), 13, 1024),
        ("single-5k", seeded(5000), 9, 3),
        ("single-50k", seeded(50000), 9, 1),
        ("multi-mixed", mixed(), 13, 256),
    ] {
        let mut both: Vec<[u64; 4]> = vec![];
        let mut a = stock::prep(&r, "projected");
        let mut b = candidate::prep(&r, "projected");
        let mut c = baseline::prep(&r, "projected");
        let mut d = composed::prep(&r, "projected");
        for i in 0..(pairs + 2) {
            let mut times = [0; 4];
            for arm in (0..4).map(|k| if i % 2 == 0 { k } else { 3 - k }) {
                for _ in 0..reps {
                    match arm {
                        0 => a.rearm(),
                        1 => b.rearm(),
                        2 => c.rearm(),
                        _ => d.rearm(),
                    }
                    let t = cpu_ns();
                    let o = match arm {
                        0 => a.run(None),
                        1 => b.run(None),
                        2 => c.run(None),
                        _ => d.run(None),
                    }
                    .unwrap();
                    black_box(o);
                    times[arm] += cpu_ns() - t;
                }
            }
            if i >= 2 {
                both.push(times)
            }
        }
        let med = |mut v: Vec<u64>| {
            v.sort_unstable();
            v[v.len() / 2] / reps as u64
        };
        let mut ratios: [Vec<f64>; 2] = [
            both.iter().map(|t| t[1] as f64 / t[0] as f64).collect(),
            both.iter().map(|t| t[3] as f64 / t[2] as f64).collect(),
        ];
        for xs in &mut ratios {
            xs.sort_by(f64::total_cmp);
        }
        let ratios_med = ratios.each_ref().map(|a| a[pairs / 2]);
        let ratios_p90 = ratios.each_ref().map(|a| a[(9 * (pairs - 1)) / 10]);
        println!(
            "CPU {label} reps={reps} median-per-render-ns=[{},{},{},{}] paired-median={ratios_med:?} paired-p90={ratios_p90:?} summed-samples={both:?}",
            med(both.iter().map(|x| x[0]).collect()),
            med(both.iter().map(|x| x[1]).collect()),
            med(both.iter().map(|x| x[2]).collect()),
            med(both.iter().map(|x| x[3]).collect())
        );
        assert!(
            ratios_med.iter().all(|x| *x <= MEDIAN_LIMIT)
                && ratios_p90.iter().all(|x| *x <= P90_LIMIT),
            "scoped CPU regression: {label}"
        );
    }
    println!("CPU PASS");
}
fn main() {
    match std::env::args().nth(1).as_deref() {
        Some("semantics") => semantics(),
        Some("allocation") => allocation(),
        Some("cpu") => cpu(),
        _ => panic!("semantics|allocation|cpu"),
    }
}
