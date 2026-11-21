use agent_client_protocol::schema::v1::SessionUpdate;
use domain::{
    Event, EventContext, EventEnvelope, MessageId, SessionId, new_message_id, new_session_id,
    new_thread_id, new_turn_id,
};
use proteus_contracts::app_protocol::AppServerEvent;
pub use proteus_contracts::domain;
use std::{
    alloc::{GlobalAlloc, Layout, System},
    hint::black_box,
    sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
};
mod candidate;
mod stock;

type Output = agent_client_protocol::Result<Vec<SessionUpdate>>;
trait Side {
    fn run(&mut self, e: EventEnvelope) -> Output;
    fn fallback(&self) -> Option<SessionUpdate>;
    fn settle(&mut self) -> Vec<SessionUpdate>;
}

fn start(c: &EventContext) -> EventEnvelope {
    EventEnvelope::new(
        c.clone(),
        0,
        Event::TurnStarted {
            session_id: c.session_id,
            thread_id: c.thread_id,
            turn_id: new_turn_id(),
        },
    )
}
fn delta(reasoning: bool, id: MessageId, offset: usize, text: String) -> Event {
    if reasoning {
        Event::AssistantReasoningTextDelta {
            message_id: id,
            offset,
            text,
        }
    } else {
        Event::AssistantTextDelta {
            message_id: id,
            phase: None,
            offset,
            text,
        }
    }
}
fn done(reasoning: bool, id: MessageId, text: String) -> Event {
    if reasoning {
        Event::AssistantReasoningMessageCompleted {
            message_id: id,
            text,
        }
    } else {
        Event::AssistantMessageCompleted {
            message_id: id,
            phase: None,
            text,
        }
    }
}
fn json(x: Output) -> (bool, String) {
    match x {
        Ok(v) => (true, serde_json::to_string(&v).unwrap()),
        Err(e) => (false, serde_json::to_string(&e).unwrap()),
    }
}

#[test]
fn differential() {
    let c = EventContext::new(new_session_id(), new_thread_id(), None);
    let id = new_message_id();
    let second = new_message_id();
    let mut traces = 0;
    let (mut ok, mut errors) = (0, 0);
    for thought in [false, true] {
        for prefix in ["", "a", "aa", "я", "e\u{301}", "🐈", "ab界cd", "👨‍👩"] {
            for offset in 0..=prefix.len() + 2 {
                for tail in [
                    "", "a", "aa", "я", "я!", "界cdé", "e\u{301}", "🐈", "🐈!", "👨", "xy", prefix,
                ] {
                    let mut a = stock::fresh(c.session_id);
                    let mut b = candidate::fresh(c.session_id);
                    let event = |e| EventEnvelope::new(c.clone(), 0, e);
                    let mut other_thread = c.clone();
                    other_thread.thread_id = new_thread_id();
                    let other_session = EventContext::new(new_session_id(), c.thread_id, None);
                    let mut combined = prefix.to_owned();
                    if offset <= prefix.len() && prefix.is_char_boundary(offset) {
                        let shared = (prefix.len() - offset).min(tail.len());
                        if tail.is_char_boundary(shared) {
                            combined.push_str(&tail[shared..]);
                        }
                    }
                    let trace = [
                        start(&c),
                        event(delta(thought, id, 0, prefix.into())),
                        EventEnvelope::new(
                            other_thread,
                            0,
                            delta(thought, id, offset, "ignored".into()),
                        ),
                        EventEnvelope::new(
                            other_session,
                            0,
                            delta(thought, id, offset, "ignored".into()),
                        ),
                        event(delta(thought, id, offset, tail.into())),
                        event(done(thought, id, combined)),
                        event(delta(!thought, id, 0, "split stream".into())),
                        event(delta(false, second, 0, "turn".into())),
                        event(done(thought, id, format!("{prefix}!"))),
                        event(delta(thought, id, prefix.len(), "!".into())),
                    ];
                    for e in trace {
                        let x = json(a.run(e.clone()));
                        let y = json(b.run(e));
                        assert_eq!(
                            x, y,
                            "thought={thought} prefix={prefix:?} offset={offset} tail={tail:?}"
                        );
                        if x.0 { ok += 1 } else { errors += 1 }
                    }
                    assert_eq!(
                        serde_json::to_vec(&a.fallback()).unwrap(),
                        serde_json::to_vec(&b.fallback()).unwrap()
                    );
                    assert_eq!(
                        serde_json::to_vec(&a.settle()).unwrap(),
                        serde_json::to_vec(&b.settle()).unwrap()
                    );
                    traces += 1;
                }
            }
        }
    }
    assert!(errors > 1000);
    println!(
        "{traces} paired traces; {ok} equivalent successful batches and {errors} equivalent serialized errors; {traces} fallback comparisons"
    );
}

struct Counting;
static ACTIVE: AtomicBool = AtomicBool::new(false);
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn record(n: usize) {
    if ACTIVE.load(Relaxed) {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(n, Relaxed);
    }
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        record(l.size());
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        record(l.size());
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        record(n);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[global_allocator]
static ALLOC: Counting = Counting;

#[derive(Debug, Clone, Copy)]
enum Scenario {
    Broadcast,
    Spare,
    Partial,
    Duplicate,
    Completed,
    Empty,
}
fn count(
    mut p: impl Side,
    c: &EventContext,
    sc: Scenario,
    reason: bool,
    n: usize,
    width: usize,
) -> (usize, usize, usize) {
    let id = new_message_id();
    let t = "x".repeat(width);
    assert!(p.run(start(c)).unwrap().is_empty());
    let (tx, mut rx) = tokio::sync::broadcast::channel(1);
    let mut events = Vec::with_capacity(n);
    for i in 0..n {
        let event = match sc {
            Scenario::Spare => {
                let mut s = String::with_capacity(width + 8192);
                s.push_str(&t);
                delta(reason, id, i * width, s)
            }
            Scenario::Empty => delta(reason, id, 0, String::new()),
            Scenario::Partial if i > 0 => delta(reason, id, i * width - 1, format!("x{t}")),
            Scenario::Duplicate => delta(reason, id, 0, t.clone()),
            Scenario::Completed => done(reason, id, t.clone()),
            _ => delta(reason, id, i * width, t.clone()),
        };
        let env = EventEnvelope::new(c.clone(), i as u64, event);
        if let Scenario::Broadcast = sc {
            tx.send(AppServerEvent::Runtime {
                envelope: Box::new(env),
            })
            .unwrap();
            let AppServerEvent::Runtime { envelope } = rx.try_recv().unwrap() else {
                unreachable!()
            };
            events.push(*envelope);
        } else {
            events.push(env)
        }
    }
    CALLS.store(0, Relaxed);
    BYTES.store(0, Relaxed);
    ACTIVE.store(true, Relaxed);
    let mut outputs = 0;
    for e in events {
        outputs += black_box(p.run(black_box(e)).unwrap()).len();
    }
    ACTIVE.store(false, Relaxed);
    (CALLS.load(Relaxed), BYTES.load(Relaxed), outputs)
}
#[test]
fn requests_abba() {
    let c = EventContext::new(new_session_id(), new_thread_id(), None);
    for reason in [false, true] {
        let run = |new| {
            if new {
                count(
                    candidate::fresh(c.session_id),
                    &c,
                    Scenario::Broadcast,
                    reason,
                    1,
                    1024 * 1024,
                )
            } else {
                count(
                    stock::fresh(c.session_id),
                    &c,
                    Scenario::Broadcast,
                    reason,
                    1,
                    1024 * 1024,
                )
            }
        };
        let (a, b, b2, a2) = (run(false), run(true), run(true), run(false));
        assert_eq!(a, a2);
        assert_eq!(b, b2);
        assert_eq!(a.2, b.2);
        assert_eq!(a.0 - b.0, 1);
        assert_eq!(a.1 - b.1, 1024 * 1024);
        println!(
            "1 MiB broadcast chunk thought={reason}: calls {} -> {}; requested B {} -> {}",
            a.0, b.0, a.1, b.1
        );
    }
    for sc in [
        Scenario::Broadcast,
        Scenario::Spare,
        Scenario::Partial,
        Scenario::Duplicate,
        Scenario::Completed,
        Scenario::Empty,
    ] {
        for reason in [false, true] {
            let run = |new| {
                if new {
                    count(candidate::fresh(c.session_id), &c, sc, reason, 1024, 32)
                } else {
                    count(stock::fresh(c.session_id), &c, sc, reason, 1024, 32)
                }
            };
            let (a, b, b2, a2) = (run(false), run(true), run(true), run(false));
            assert_eq!(a, a2);
            assert_eq!(b, b2);
            assert_eq!(a.2, b.2);
            let saved = match sc {
                Scenario::Broadcast => 1024,
                Scenario::Partial | Scenario::Duplicate => 1,
                _ => 0,
            };
            assert_eq!(a.0 - b.0, saved);
            assert_eq!(a.1 - b.1, saved * 32);
            println!(
                "{sc:?} thought={reason}: calls {} -> {}; requested B {} -> {}; batches with output {}",
                a.0, b.0, a.1, b.1, b.2
            );
        }
    }
}
