pub use proteus_contracts::{contracts, model_standard};
mod controls;
#[path = "../../worker/native/route/core.rs"]
mod core;
mod meter;
use contracts::{ConversationReader, SessionStorageFailure};
use core::{SessionStore, TestMode as M, candidate, model_context::ModelContextState, stock};
use meter::{Stat, mark};
use model_standard::CanonicalMessage;
use serde_json::{Value, json};
use std::{
    hint::black_box,
    sync::{
        Arc,
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
    },
    task::{Context, Poll, Wake, Waker},
};
use tokio::sync::Mutex;
type Hist = Arc<Mutex<Vec<CanonicalMessage>>>;
type Ctx = Arc<Mutex<ModelContextState>>;
struct WakeN(AtomicUsize);
impl Wake for WakeN {
    fn wake(self: Arc<Self>) {
        self.0.fetch_add(1, Ordering::SeqCst);
    }
    fn wake_by_ref(self: &Arc<Self>) {
        self.0.fetch_add(1, Ordering::SeqCst);
    }
}
#[derive(Clone, Copy, PartialEq, Debug)]
enum Op {
    Park,
    Cancel,
    Now,
    NoStore,
}
struct R {
    box_: Stat,
    pending: Stat,
    finish: Stat,
    caps: u64,
    trace: Vec<&'static str>,
    outcome: String,
}
impl R {
    fn json(&self) -> Value {
        json!({"future_box":self.box_.json(),"to_pending":self.pending.json(),"to_exit":self.finish.json(),"capacities_hash":self.caps.to_string(),"trace":self.trace,"outcome":self.outcome})
    }
}
fn error_text(m: M) -> Option<&'static str> {
    match m {
        M::WorkerError => Some("session no longer exists"),
        M::WrongResponse => Some("storage returned an unexpected snapshot response"),
        M::WrongSession => Some("storage snapshot belongs to another session"),
        _ => None,
    }
}

async fn arm(new: bool, mode: M, op: Op, history: &Hist, context: &Ctx) -> R {
    let (store, io) = SessionStore::fixture(mode);
    let storeopt = if op == Op::NoStore {
        None
    } else {
        Some(store.clone())
    };
    let resident = Arc::new(AtomicBool::new(true));
    let revision = Arc::new(AtomicU64::new(29));
    let reader: Box<dyn ConversationReader> = if new {
        Box::new(candidate::TurnConversation {
            history: history.clone(),
            context: context.clone(),
            resident,
            revision,
            store: storeopt,
        })
    } else {
        Box::new(stock::TurnConversation {
            history: history.clone(),
            context: context.clone(),
            resident,
            revision,
            store: storeopt,
        })
    };
    let mut park = if matches!(op, Op::Park | Op::Cancel) {
        Some(store.park().await)
    } else {
        None
    };
    let wake = Arc::new(WakeN(AtomicUsize::new(0)));
    let waker = Waker::from(wake.clone());
    let mut cx = Context::from_waker(&waker);
    let from_box = mark();
    let mut fut = reader.read();
    let box_ = mark().minus(from_box);
    let mut pending = Stat::default();
    if park.is_some() {
        let t = mark();
        let first = fut.as_mut().poll(&mut cx);
        pending = mark().minus(t);
        assert!(first.is_pending() && history.try_lock().is_err() && context.try_lock().is_err());
        assert_eq!(io.n_events(), 0);
        assert_eq!(wake.0.load(Ordering::SeqCst), 0);
        if op == Op::Cancel {
            let t = mark();
            drop(fut);
            let finish = mark().minus(t);
            assert_eq!(box_.net() + pending.net() + finish.net(), 0);
            assert!(history.try_lock().is_ok() && context.try_lock().is_ok());
            drop(park.take());
            assert_eq!(io.n_events(), 0);
            assert_eq!(wake.0.load(Ordering::SeqCst), 0);
            assert!(store.writer_available());
            let out = reader.read().await.unwrap();
            assert_eq!(out.revision, 41);
            assert_eq!(out.messages, *history.try_lock().unwrap());
            assert_eq!(out.model_context, controls::observations());
            return R {
                box_,
                pending,
                finish,
                caps: 0,
                trace: io.trace(),
                outcome: "cancelled; retry revision 41".into(),
            };
        }
        drop(park.take());
        assert_eq!(wake.0.load(Ordering::SeqCst), 1);
    }
    let t = mark();
    let second = fut.as_mut().poll(&mut cx);
    let finish = mark().minus(t);
    let Poll::Ready(result) = second else {
        panic!("expected ready after unlock/immediate read")
    };
    assert!(history.try_lock().is_ok() && context.try_lock().is_ok() && store.writer_available());
    drop(fut);
    let trace = io.trace();
    assert!(io.free_at_calls().into_iter().all(|v| v));
    assert!(io.caller_at_calls().into_iter().all(|v| v));
    let (caps, outcome) = if let Some(expected) = error_text(mode) {
        let e = result.unwrap_err();
        assert_eq!(e.to_string(), expected);
        assert_eq!(trace, ["open"]);
        if mode == M::WorkerError {
            assert_eq!(
                e.downcast_ref::<SessionStorageFailure>(),
                Some(&SessionStorageFailure::MissingSession)
            );
        }
        (0, e.to_string())
    } else {
        let out = result.unwrap();
        let rev = if op == Op::NoStore {
            29
        } else if mode == M::Lease {
            41
        } else {
            73
        };
        assert_eq!(out.revision, rev);
        if op == Op::NoStore || mode == M::Lease {
            assert!(trace.is_empty())
        } else {
            assert_eq!(trace, ["open", "release"])
        }
        (
            controls::caps(&*history.try_lock().unwrap(), &out),
            format!("ok revision {rev}"),
        )
    };
    R {
        box_,
        pending,
        finish,
        caps,
        trace,
        outcome,
    }
}

async fn go() {
    for (n, mixed) in [
        (0, false),
        (1, false),
        (5000, false),
        (50000, false),
        (63, true),
    ] {
        let h = Arc::new(Mutex::new(controls::seed(n, mixed)));
        let c = Arc::new(Mutex::new(ModelContextState::from_snapshot(
            controls::observations(),
        )));
        let reference = {
            let g = h.lock().await;
            let t = mark();
            let owned = g.clone();
            black_box(&owned);
            let s = mark().minus(t);
            drop(owned);
            s
        };
        assert_eq!(reference.d, 0);
        assert_eq!(reference.net() == 0, n == 0);
        for (mode, op) in [
            (M::Lease, Op::Park),
            (M::Good, Op::Park),
            (M::Lease, Op::Cancel),
            (M::WorkerError, Op::Now),
            (M::WrongResponse, Op::Now),
            (M::WrongSession, Op::Now),
            (M::WorkerError, Op::Park),
            (M::Lease, Op::Now),
            (M::Good, Op::Now),
            (M::ReleaseError, Op::Now),
            (M::Good, Op::NoStore),
        ] {
            let a = arm(false, mode, op, &h, &c).await;
            let b = arm(true, mode, op, &h, &c).await;
            assert_eq!(
                (&a.trace, a.caps, &a.outcome),
                (&b.trace, b.caps, &b.outcome)
            );
            if matches!(op, Op::Park | Op::Cancel) {
                assert_eq!(a.pending.minus(b.pending), reference);
                assert_eq!(b.pending, Stat::default());
            }
            if op == Op::Cancel {
                assert_eq!(a.box_.net() + a.pending.net() + a.finish.net(), 0);
                assert_eq!(b.box_.net() + b.pending.net() + b.finish.net(), 0);
            } else if error_text(mode).is_some() {
                let stock_all = a.pending.a + a.finish.a;
                let cand_all = b.pending.a + b.finish.a;
                assert_eq!(stock_all - cand_all, reference.a);
                assert_eq!(
                    a.pending.na + a.finish.na - b.pending.na - b.finish.na,
                    reference.na
                );
                assert_eq!(
                    a.pending.net() + a.finish.net(),
                    b.pending.net() + b.finish.net()
                );
            } else {
                assert_eq!(a.pending.a + a.finish.a, b.pending.a + b.finish.a);
                assert_eq!(a.pending.na + a.finish.na, b.pending.na + b.finish.na);
                assert_eq!(
                    a.pending.net() + a.finish.net(),
                    b.pending.net() + b.finish.net()
                );
            }
            println!(
                "{}",
                json!({"layout":if cfg!(feature="preserve_order"){"preserve_order"}else{"default"},"rows":n,"mixed":mixed,"mode":format!("{mode:?}"),"op":format!("{op:?}"),"reference":reference.json(),"stock":a.json(),"candidate":b.json()})
            );
        }
    }
}
fn main() {
    assert!(std::env::args().len() == 1);
    tokio::runtime::Builder::new_current_thread()
        .build()
        .unwrap()
        .block_on(tokio::task::unconstrained(go()));
}
