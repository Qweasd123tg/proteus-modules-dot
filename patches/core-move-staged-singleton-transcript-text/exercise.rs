use serde_json::json;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    fs::OpenOptions,
    hint::black_box,
    sync::atomic::{AtomicUsize, Ordering},
    time::Instant,
};
#[derive(Debug, Copy, Clone, Default, PartialEq, Eq)]
struct Count {
    allocs: usize,
    reallocs: usize,
    bytes: usize,
}
thread_local! {
    static ACTIVE:Cell<bool>=const{Cell::new(false)};
    static COUNT:Cell<Count>=Cell::new(Count::default());
    static LATE:Cell<bool>=const{Cell::new(false)};
}
struct Meter;
fn add(size: usize, re: bool) {
    if ACTIVE.try_with(Cell::get).unwrap_or(false) {
        COUNT.with(|cell| {
            let mut s = cell.get();
            s.bytes += size;
            if re {
                s.reallocs += 1
            } else {
                s.allocs += 1
            };
            cell.set(s);
        });
    }
}
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        add(l.size(), false);
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        add(l.size(), false);
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, s: usize) -> *mut u8 {
        add(s, true);
        unsafe { System.realloc(p, l, s) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static ALLOCATOR: Meter = Meter;
static NEXT: AtomicUsize = AtomicUsize::new(0);
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
        schema_version: 21,
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
struct Spool {
    path: PathBuf,
    stage: DisplayRecords,
    cert: Option<HashMap<TurnId, ThreadId>>,
    size: u64,
}
impl Drop for Spool {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}
impl Spool {
    fn new(records: &[JournalRecord], tail: &[u8], offset: isize) -> Self {
        let path = PathBuf::from(std::env::var_os("R260_TMP").expect("private scratch"))
            .join(format!("input-{}", NEXT.fetch_add(1, Ordering::Relaxed)));
        let f = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .open(&path)
            .unwrap();
        let mut c = Some(CausalStage::new());
        let mut f = std::io::BufWriter::new(f);
        for r in records {
            serde_json::to_writer(&mut f, r).unwrap();
            f.write_all(b"\n").unwrap();
            if c.as_mut().is_some_and(|x| !x.note(r)) {
                c = None;
            }
        }
        f.write_all(tail).unwrap();
        let mut f = f.into_inner().unwrap();
        let size = f.stream_position().unwrap();
        Self {
            path,
            stage: DisplayRecords {
                file: f,
                count: records.len().checked_add_signed(offset).unwrap(),
            },
            cert: c.and_then(CausalStage::finish),
            size,
        }
    }
}
type Render = fn(
    &mut DisplayRecords,
    HashMap<TurnId, ThreadId>,
    Option<TurnId>,
    bool,
    &mut dyn FnMut(&mut JournalRecord),
) -> Result<Vec<AppTranscriptMessage>>;
const ARMS: [Render; 2] = [stock::run, candidate::run];
fn run(
    i: usize,
    s: &mut Spool,
    live: Option<TurnId>,
    general: bool,
) -> Result<Vec<AppTranscriptMessage>> {
    ARMS[i](
        &mut s.stage,
        s.cert.clone().unwrap_or_default(),
        live,
        general,
        &mut |_| {},
    )
}
fn golden(
    name: &str,
    records: &[JournalRecord],
    live: Option<TurnId>,
    cert: bool,
) -> Vec<AppTranscriptMessage> {
    let mut s = Spool::new(records, b"", 0);
    assert_eq!(s.cert.is_some(), cert, "{name} causality");
    let baseline = run(0, &mut s, live, true).unwrap();
    let wire = serde_json::to_vec(&baseline).unwrap();
    for (arm, general) in [(0, false), (1, false), (1, true)] {
        if !cert && !general {
            continue;
        }
        let got = run(arm, &mut s, live, general).unwrap();
        assert_eq!(
            serde_json::to_vec(&got).unwrap(),
            wire,
            "{name} arm {arm}/{general}"
        );
    }
    baseline
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
fn semantics() {
    let fixture = mixed();
    let rows = golden("mixed", &fixture, Some(id(8)), true);
    let text: Vec<&str> = rows.iter().map(|r| r.text.as_str()).collect();
    assert_eq!(
        text,
        [
            "earlier reasoning",
            "  Дата 🌊\0 \u{2009}",
            " before ",
            "",
            "после\n三",
            "developer commentary",
            "append compactor stays",
            "kept replace",
            "kept checkpoint",
            "AppServer error: failed reason",
            "AppServer timeout: turn timed out"
        ]
    );
    assert_eq!(rows[0].timestamp_ms, Some(986));
    assert_eq!(rows[1].timestamp_ms, Some(986));
    assert_eq!(rows[1].phase, Some(MessagePhase::FinalAnswer));
    assert_eq!(rows[3].tool.as_ref().unwrap().status, "done");
    assert_eq!(rows[4].images[0].id, "i");
    assert_eq!(rows[5].role, "system");
    let m = single(11, "response then append");
    let records = [
        rec(1, Some(1), open()),
        rec(2, Some(1), response(m.clone())),
        rec(3, Some(1), append(vec![single(10, "middle"), m])),
    ];
    let r = golden("causal response", &records, None, true);
    assert_eq!(r.len(), 2);
    assert_eq!(r[0].text, "response then append");
    assert_eq!(r[0].timestamp_ms, Some(986));
    let reset = [
        rec(1, None, append(vec![single(1, "destroy")])),
        rec(
            2,
            None,
            mutation(
                HistoryMutationKind::Replace,
                vec![single(1, "replacement")],
                false,
            ),
        ),
        rec(3, None, append(vec![single(44, "tail")])),
    ];
    let r = golden("hard reset fallback", &reset, None, false);
    assert_eq!(r.len(), 2);
    assert_eq!(r[0].text, "replacement");
    let hosted = ContentPart::HostedToolActivity {
        activity: HostedToolActivity::WebSearch {
            id: "ws".into(),
            status: HostedToolStatus::Completed,
            action: WebSearchAction::OpenPage {
                url: "https://example.invalid/".into(),
            },
        },
    };
    let citation = ContentPart::Citation {
        citation: Citation::Url {
            start_index: 0,
            end_index: 3,
            title: "title".into(),
            url: "test".into(),
        },
    };
    let r = golden(
        "hosted/citation fallback",
        &[rec(
            1,
            None,
            append(vec![msg(
                12,
                MessageRole::Assistant,
                vec![part(12, hosted), part(13, tx("link")), part(14, citation)],
            )]),
        )],
        None,
        false,
    );
    assert_eq!(
        r[0].tool.as_ref().unwrap().metadata["citations"][0]["title"],
        "title"
    );
    for n in 0..96 {
        let mut a = single(1, if n & 1 == 0 { " \u{2002}" } else { "\0 ok " });
        a.parts[0].scope = [
            PartScope::Conversation,
            PartScope::Trace,
            PartScope::Request,
        ][n % 3];
        let mut b = single(2, "B");
        if n & 4 != 0 {
            b.parts[0].part_id = a.parts[0].part_id;
        }
        if n & 8 != 0 {
            b.id = a.id;
        }
        if n & 16 != 0 {
            b.parts.push(part(34, tx("tail")));
        }
        golden(
            "generated",
            &[
                rec(1, Some(8), append(vec![a])),
                rec(2, None, append(vec![b])),
            ],
            (n & 32 != 0).then(|| id(8)),
            true,
        );
    }
    for (tail, count, expected) in [
        (&b"garbage\n"[..], 0, "expected value"),
        (&b"{"[..], 0, "incomplete transcript staging record"),
        (&b""[..], 1, "transcript staging record count changed"),
    ] {
        let mut s = Spool::new(
            &[rec(1, None, append(vec![single(10, "pre-error")]))],
            tail,
            count,
        );
        for arm in [0, 1] {
            let mut calls = 0;
            let x = ARMS[arm](&mut s.stage, HashMap::new(), None, false, &mut |_| {
                calls += 1
            })
            .unwrap_err();
            assert_eq!(calls, 1);
            assert!(x.to_string().contains(expected), "{x}");
        }
    }
    LATE.set(true);
    let mut s = Spool::new(
        &[rec(1, None, append(vec![single(1, "never published")]))],
        b"",
        0,
    );
    for arm in [0, 1] {
        let mut visits = 0;
        assert_eq!(
            ARMS[arm](&mut s.stage, HashMap::new(), None, false, &mut |_| {
                visits += 1
            })
            .unwrap_err()
            .to_string(),
            "injected late scan error"
        );
        assert_eq!(visits, 1);
    }
    LATE.set(false);
    println!(
        "SEMANTICS 96 generated; actual staged certification, complete serialized output + pinned general oracle; mixed/live/clock/compaction/settlement/reset/hosted; 4 post-row failures"
    );
}
fn long(n: usize) -> Vec<JournalRecord> {
    vec![rec(
        1,
        None,
        append(
            (0..n)
                .map(|i| {
                    single(
                        i as u128,
                        format!(
                            "Fixture row {i}\n{}",
                            "Синтетический текст для замера памяти и прокрутки. ".repeat(4)
                        ),
                    )
                })
                .collect(),
        ),
    )]
}
fn witness(n: usize, excess: usize) {
    let mut s = Spool::new(&long(n), b"", 0);
    assert!(s.cert.is_some());
    let mut counts = Vec::new();
    let mut serialized = None;
    let mut byte_total = 0;
    let mut capacity = [0; 2];
    for arm in [0, 1] {
        let mut p = Vec::with_capacity(n);
        COUNT.set(Count::default());
        let rows = ARMS[arm](&mut s.stage, HashMap::new(), None, false, &mut |r| {
            let JournalEntry::HistoryMutated(h) = &mut r.entry else {
                panic!()
            };
            for m in &mut h.messages {
                let ContentPart::Text { text } = &mut m.parts[0].payload else {
                    panic!()
                };
                if excess > 0 {
                    text.reserve_exact(excess);
                }
                p.push((text.as_ptr() as usize, text.len(), text.capacity()));
            }
            ACTIVE.set(true);
        })
        .unwrap();
        ACTIVE.set(false);
        let c = COUNT.get();
        counts.push(c);
        let wire = serde_json::to_vec(&rows).unwrap();
        if let Some(ref stock) = serialized {
            assert_eq!(&wire, stock)
        } else {
            serialized = Some(wire);
        }
        assert_eq!(rows.len(), n);
        byte_total = p.iter().map(|q| q.1).sum::<usize>();
        for (row, (ptr, len, cap)) in rows.iter().zip(p) {
            assert_eq!(row.text.len(), len);
            assert_eq!(row.text.as_ptr() as usize == ptr, arm == 1 && cap == len);
            assert_eq!(row.text.capacity(), len);
            capacity[arm] += row.text.capacity();
        }
    }
    assert_eq!(
        counts[0].allocs - counts[1].allocs,
        if excess == 0 { n } else { 0 }
    );
    assert_eq!(counts[0].reallocs, counts[1].reallocs);
    assert_eq!(
        counts[0].bytes - counts[1].bytes,
        if excess == 0 { byte_total } else { 0 }
    );
    if n == 50000 {
        assert_eq!(byte_total, 19_688_890);
    }
    println!(
        "WITNESS rows={n} extra={excess} stage={} text={byte_total} capacities={capacity:?} stock={:?} candidate={:?}",
        s.size, counts[0], counts[1]
    );
}
#[repr(C)]
struct Ts {
    sec: i64,
    nsec: i64,
}
unsafe extern "C" {
    fn clock_gettime(clockid: i32, t: *mut Ts) -> i32;
}
fn cpu() -> u64 {
    let mut t = Ts { sec: 0, nsec: 0 };
    assert_eq!(unsafe { clock_gettime(2, &mut t) }, 0);
    (t.sec as u64) * 1_000_000_000 + t.nsec as u64
}
thread_local! {static TIMED:Cell<bool>=const{Cell::new(false)};static INNER:Cell<u64>=const{Cell::new(0)};}
fn timing(name: &str, records: Vec<JournalRecord>, loops: usize, pairs: usize) {
    let mut stage = Spool::new(&records, b"", 0);
    let certified = stage.cert.is_some();
    assert!(certified);
    drop(records);
    let mut all = Vec::new();
    TIMED.set(true);
    for i in 0..pairs + 3 {
        let mut measurements = [[0u64; 3]; 2];
        let first = (i / 2 + i) % 2;
        for arm in [first, 1 - first] {
            INNER.set(0);
            let t = Instant::now();
            let c = cpu();
            for _ in 0..loops {
                let rows = run(arm, &mut stage, None, false).unwrap();
                black_box(rows);
            }
            let dur = cpu() - c;
            measurements[arm] = [t.elapsed().as_nanos() as u64, dur, INNER.get()];
        }
        if i >= 3 {
            all.push((first, measurements));
        }
    }
    TIMED.set(false);
    let mut out = Vec::new();
    for idx in 0..3 {
        let mut ratio = Vec::new();
        let mut order: [Vec<f64>; 2] = Default::default();
        let mut absol: [Vec<u64>; 2] = Default::default();
        for (first, times) in &all {
            let r = times[1][idx] as f64 / times[0][idx] as f64;
            ratio.push(r);
            order[*first].push(r);
            absol[0].push(times[0][idx] / loops as u64);
            absol[1].push(times[1][idx] / loops as u64);
        }
        ratio.sort_by(f64::total_cmp);
        for x in &mut order {
            x.sort_by(f64::total_cmp);
        }
        for x in &mut absol {
            x.sort();
        }
        let q = |a: &[f64], p: usize| a[(a.len() - 1) * p / 100];
        out.push(json!({"instrument":(["whole_wall","whole_cpu","visit_cpu"][idx]),"pairs":pairs,"loops":loops,
          "median_ns_stock":absol[0][pairs/2],"median_ns_candidate":absol[1][pairs/2],
          "ratio_p10":q(&ratio,10),"ratio_median":q(&ratio,50),"ratio_p90":q(&ratio,90),
          "stock_first_median":q(&order[0],50),"candidate_first_median":q(&order[1],50)}));
    }
    println!("TIMING {name} {}", serde_json::to_string(&out).unwrap());
}
fn main() {
    if std::env::args().any(|v| v == "--timing") {
        timing("small", long(16), 150, 25);
        timing("mixed", mixed(), 50, 25);
        timing("50k", long(50000), 1, 25);
    } else {
        semantics();
        witness(16, 0);
        witness(1, 1_048_576);
        witness(50000, 0);
    }
}
