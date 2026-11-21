use std::cell::Cell;
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Work {
    pub tail: usize,
    pub hidden: usize,
    pub link: usize,
    pub peer: usize,
}
thread_local! { static COUNT: Cell<Work> = const {
    Cell::new(Work { tail: 0, hidden: 0, link: 0, peer: 0 })
}; }
fn add(by: impl FnOnce(&mut Work)) {
    let mut work = COUNT.get();
    by(&mut work);
    COUNT.set(work);
}
pub fn reset() { COUNT.set(Work::default()); }
pub fn work() -> Work { COUNT.get() }
pub fn tail() { add(|w| w.tail += 1); }
pub fn hidden() { add(|w| w.hidden += 1); }
pub fn link() { add(|w| w.link += 1); }
pub fn peer() { add(|w| w.peer += 1); }
