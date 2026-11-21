use std::cell::Cell;
use std::sync::Arc;

thread_local! {
    static WORK: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}

pub fn run<T>(f: impl FnOnce() -> T) -> (T, (usize, usize)) {
    WORK.with(|work| {
        assert!(work.replace(Some((0, 0))).is_none());
        let value = f();
        (value, work.replace(None).unwrap())
    })
}

pub fn text(value: String) -> Arc<str> {
    WORK.with(|work| {
        if let Some((calls, bytes)) = work.get() {
            work.set(Some((calls + 1, bytes + value.len())));
        }
    });
    value.into()
}
