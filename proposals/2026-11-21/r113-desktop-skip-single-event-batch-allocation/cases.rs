use serde_json::json;
use std::cell::{Cell, RefCell};
use std::future::Future;
use std::mem::{size_of, size_of_val};
use std::pin::{Pin, pin};
use std::task::{Context as TaskContext, Poll, Waker};

mod lifted {
    include!("pump.rs");
}
mod stream_batch {
    include!("scheduler.rs");
}
const THREAD: &str = "fixture-thread";
const FALLBACK: &str = "Codex app-server закрыл соединение";

#[derive(Debug)]
struct Context {
    applied: RefCell<Vec<Event>>,
    boundaries: RefCell<Vec<usize>>,
    updates: Cell<usize>,
    reject: Option<usize>,
}
impl Context {
    fn new(reject: Option<usize>) -> Self {
        Self {
            applied: RefCell::new(Vec::with_capacity(256)),
            boundaries: RefCell::new(Vec::with_capacity(32)),
            updates: Cell::new(0),
            reject,
        }
    }
    fn notify(&self) {
        self.boundaries
            .borrow_mut()
            .push(self.applied.borrow().len());
    }
}
struct Recorder;
impl Recorder {
    fn update(&self, cx: &Context, f: impl FnOnce(&Self, &Context)) -> Result<(), ()> {
        let next = cx.updates.get() + 1;
        cx.updates.set(next);
        if cx.reject == Some(next) {
            Err(())
        } else {
            f(self, cx);
            Ok(())
        }
    }
    fn apply_codex(&self, event: Event, cx: &Context) {
        cx.applied.borrow_mut().push(event);
    }
}
#[derive(Default, Debug, PartialEq, Eq, Clone, Copy)]
struct Counts {
    waiting: usize,
    got: usize,
    end: usize,
    extra: usize,
    ok: usize,
    empty: usize,
    closed: usize,
    reason: usize,
}
struct Observed<'a> {
    events: &'a Events,
    route: &'a RefCell<Router>,
    after_first: RefCell<Option<Event>>,
    counts: Cell<Counts>,
}
impl<'a> Observed<'a> {
    fn new(events: &'a Events, route: &'a RefCell<Router>) -> Self {
        Self {
            events,
            route,
            after_first: RefCell::new(None),
            counts: Cell::new(Counts::default()),
        }
    }
    fn add(&self, f: impl FnOnce(&mut Counts)) {
        let mut c = self.counts.get();
        f(&mut c);
        self.counts.set(c);
    }
    async fn recv(&self) -> Result<Event, async_channel::RecvError> {
        self.add(|c| c.waiting += 1);
        let result = self.events.recv().await;
        if result.is_ok() {
            self.add(|c| c.got += 1);
            if let Some(event) = self.after_first.borrow_mut().take() {
                self.route.borrow_mut().deliver(THREAD, event);
            }
        } else {
            self.add(|c| c.end += 1);
        }
        result
    }
    fn try_recv(&self) -> Result<Event, async_channel::TryRecvError> {
        let result = self.events.try_recv();
        self.add(|c| {
            c.extra += 1;
            match result {
                Ok(_) => c.ok += 1,
                Err(async_channel::TryRecvError::Empty) => c.empty += 1,
                Err(async_channel::TryRecvError::Closed) => c.closed += 1,
            }
        });
        result
    }
    fn disconnect_reason(&self) -> Option<String> {
        self.add(|c| c.reason += 1);
        self.events.disconnect_reason()
    }
}
fn ensure_poll<F: Future<Output = ()>>(future: Pin<&mut F>, pending: bool) {
    let mut cx = TaskContext::from_waker(Waker::noop());
    assert_eq!(
        future.poll(&mut cx),
        if pending {
            Poll::Pending
        } else {
            Poll::Ready(())
        }
    );
}
fn pair() -> (RefCell<Router>, Events, usize) {
    let mut router = Router::default();
    let (events, _, generation) = router.register(THREAD).unwrap();
    (RefCell::new(router), events, generation)
}
fn sample(i: usize) -> Event {
    let method = match i % 5 {
        0 => "item/agentMessage/delta",
        1 => "item/reasoning/summaryTextDelta",
        2 => "item/commandExecution/outputDelta",
        3 => "item/plan/delta",
        _ => "item/fileChange/outputDelta",
    };
    projection::notification(
        method,
        &json!({"threadId":THREAD,"turnId":"turn:fixture",
        "itemId":format!("item:{i}"),"delta":format!("slice {i} é🦀\n")}),
    )
    .unwrap()
}
fn budget(r: &RefCell<Router>) -> usize {
    r.borrow().budget.load(Ordering::Acquire)
}
fn trace(name: &str, cx: &Context, probe: &Observed<'_>, r: &RefCell<Router>) {
    let c = probe.counts.get();
    eprintln!(
        "TRACE {name} {}",
        json!({
           "events":cx.applied.borrow().iter().map(|e|format!("{e:?}")).collect::<Vec<_>>(),
           "boundaries":*cx.boundaries.borrow(),"updates":cx.updates.get(),
           "counts":[c.waiting,c.got,c.end,c.extra,c.ok,c.empty,c.closed,c.reason], "budget":budget(r)
        })
    );
}

#[test]
fn isolated_wakes_retry_and_actual_disconnect_reason() {
    eprintln!("ARM {}", env!("R113_ARM"));
    let (router, events, _) = pair();
    let seen = Observed::new(&events, &router);
    let context = Context::new(None);
    let mut fut = pin!(lifted::run(&Recorder, &context, &seen));
    ensure_poll(fut.as_mut(), true); // open and empty, outer receive waits
    assert_eq!(context.updates.get(), 0);
    let start = Event::TurnStarted {
        id: "turn:fixture".into(),
    };
    router.borrow_mut().deliver(THREAD, start.clone());
    ensure_poll(fut.as_mut(), true);
    assert_eq!(context.updates.get(), 1);
    assert_eq!(*context.boundaries.borrow(), [1]);
    assert_eq!(
        router
            .borrow()
            .routes
            .get(THREAD)
            .unwrap()
            .current_turn
            .lock()
            .unwrap()
            .as_deref(),
        Some("turn:fixture")
    );
    assert!(router.borrow_mut().raw(RawEvent::Notification{method:"error".into(),params:
        json!({"threadId":THREAD,"turnId":"turn:fixture","willRetry":true,"error":{"message":"inert retry"}})}).is_none());
    ensure_poll(fut.as_mut(), true); // yield resolves and next outer receive waits
    assert_eq!(context.updates.get(), 1);
    let mut expected = vec![start];
    for i in 0..12 {
        expected.push(sample(i));
        router.borrow_mut().deliver(THREAD, sample(i));
        ensure_poll(fut.as_mut(), true);
        assert_eq!(context.updates.get(), i + 2);
        assert_eq!(budget(&router), 0);
        ensure_poll(fut.as_mut(), true);
        assert_eq!(context.updates.get(), i + 2);
    }
    let completed = Event::TurnCompleted {
        id: "turn:fixture".into(),
        status: "completed".into(),
        error: None,
    };
    expected.push(completed.clone());
    router.borrow_mut().deliver(THREAD, completed);
    router
        .borrow_mut()
        .disconnect_thread(THREAD, "inert fixture end".into());
    ensure_poll(fut.as_mut(), true); // queued completion still applied before close callback
    assert_eq!(context.updates.get(), 14);
    assert_eq!(seen.counts.get().closed, 1);
    ensure_poll(fut.as_mut(), false);
    expected.push(Event::Disconnected("inert fixture end".into()));
    assert_eq!(*context.applied.borrow(), expected);
    assert_eq!(*context.boundaries.borrow(), (1..=14).collect::<Vec<_>>());
    assert_eq!(context.updates.get(), 15);
    assert_eq!(
        seen.counts.get(),
        Counts {
            waiting: 15,
            got: 14,
            end: 1,
            extra: 14,
            empty: 13,
            closed: 1,
            reason: 1,
            ..Counts::default()
        }
    );
    trace("isolated-retry-close", &context, &seen, &router);
}

#[test]
fn cap_fifo_tail_empty_and_fallback() {
    let (router, events, generation) = pair();
    for i in 0..128 {
        router.borrow_mut().deliver(THREAD, sample(i));
    }
    assert!(router.borrow().contains_generation(THREAD, generation));
    let seen = Observed::new(&events, &router);
    seen.after_first.replace(Some(sample(128)));
    let context = Context::new(None);
    let mut fut = pin!(lifted::run(&Recorder, &context, &seen));
    ensure_poll(fut.as_mut(), true);
    assert_eq!(*context.boundaries.borrow(), [128]);
    assert_eq!(context.updates.get(), 1);
    assert_eq!(
        seen.counts.get(),
        Counts {
            waiting: 1,
            got: 1,
            extra: 127,
            ok: 127,
            ..Counts::default()
        }
    );
    assert_eq!(budget(&router), event_bytes(&sample(128)));
    ensure_poll(fut.as_mut(), true);
    assert_eq!(*context.boundaries.borrow(), [128, 129]);
    assert_eq!(context.updates.get(), 2);
    assert_eq!(seen.counts.get().empty, 1);
    assert_eq!(budget(&router), 0);
    router.borrow_mut().unregister(THREAD, generation);
    ensure_poll(fut.as_mut(), false);
    let mut expected = (0..129).map(sample).collect::<Vec<_>>();
    expected.push(Event::Disconnected(FALLBACK.into()));
    assert_eq!(*context.applied.borrow(), expected);
    assert_eq!(
        seen.counts.get(),
        Counts {
            waiting: 3,
            got: 2,
            end: 1,
            extra: 128,
            ok: 127,
            empty: 1,
            reason: 1,
            ..Counts::default()
        }
    );
    trace("cap-fifo-tail-fallback", &context, &seen, &router);
}

#[test]
fn rejects_update_without_notify_yield_or_consuming_tail() {
    let (router, events, _) = pair();
    for i in 0..128 {
        router.borrow_mut().deliver(THREAD, sample(i));
    }
    let seen = Observed::new(&events, &router);
    seen.after_first.replace(Some(sample(128)));
    let context = Context::new(Some(1));
    let mut fut = pin!(lifted::run(&Recorder, &context, &seen));
    ensure_poll(fut.as_mut(), false);
    assert_eq!(context.updates.get(), 1);
    assert!(context.applied.borrow().is_empty() && context.boundaries.borrow().is_empty());
    assert_eq!(
        seen.counts.get(),
        Counts {
            waiting: 1,
            got: 1,
            extra: 127,
            ok: 127,
            ..Counts::default()
        }
    );
    assert_eq!(budget(&router), event_bytes(&sample(128)));
    trace("rejected-with-tail", &context, &seen, &router);
    assert_eq!(events.try_recv().unwrap(), sample(128));
    assert_eq!(budget(&router), 0);
}

#[test]
fn metered_one_ready_poll_including_bursts_and_future_storage() {
    for n in [1, 2, 4, 5, 8, 32, 127, 128] {
        let (router, events, _) = pair();
        let expected = (0..n).map(sample).collect::<Vec<_>>();
        for event in &expected {
            router.borrow_mut().deliver(THREAD, event.clone());
        }
        let seen = Observed::new(&events, &router);
        let context = Context::new(None);
        let fut = lifted::run(&Recorder, &context, &seen);
        let future_size = size_of_val(&fut);
        let mut fut = pin!(fut);
        let (_, calls, bytes) = crate::measurement(|| ensure_poll(fut.as_mut(), true));
        assert_eq!(*context.boundaries.borrow(), [n]);
        assert_eq!(*context.applied.borrow(), expected);
        assert_eq!(budget(&router), 0);
        assert_eq!(seen.counts.get().extra, n.min(127));
        eprintln!(
            "WORK burst-{n} {}",
            json!([n, calls, bytes, size_of::<Event>(), future_size])
        );
    }
}

#[test]
fn closed_full_route_drains_without_a_probe_past_cap() {
    let (router, events, _) = pair();
    let expected = (0..128).map(sample).collect::<Vec<_>>();
    for event in &expected {
        router.borrow_mut().deliver(THREAD, event.clone());
    }
    router
        .borrow_mut()
        .disconnect_thread(THREAD, "closed with a tail".into());
    let seen = Observed::new(&events, &router);
    let context = Context::new(None);
    let mut fut = pin!(lifted::run(&Recorder, &context, &seen));
    ensure_poll(fut.as_mut(), true);
    assert_eq!(*context.applied.borrow(), expected);
    assert_eq!(*context.boundaries.borrow(), [128]);
    assert_eq!(
        seen.counts.get(),
        Counts {
            waiting: 1,
            got: 1,
            extra: 127,
            ok: 127,
            ..Counts::default()
        }
    );
    assert_eq!(budget(&router), 0);
    ensure_poll(fut.as_mut(), false);
    assert_eq!(context.updates.get(), 2);
    assert_eq!(*context.boundaries.borrow(), [128]);
    assert_eq!(
        context.applied.borrow().last(),
        Some(&Event::Disconnected("closed with a tail".into()))
    );
    assert_eq!(
        seen.counts.get(),
        Counts {
            waiting: 2,
            got: 1,
            end: 1,
            extra: 127,
            ok: 127,
            reason: 1,
            ..Counts::default()
        }
    );
    trace("closed-with-full-tail", &context, &seen, &router);
}
