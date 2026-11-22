use std::cell::Cell;

#[derive(Clone, Copy)]
#[repr(usize)]
pub enum Hit {
    Classify,
    CurrentCanon,
    DirectoryCanon,
    ConfigCanon,
    DirectoryRead,
    Entry,
    LabelAsked,
    LabelOpened,
    LabelBytes,
}

type Counts = [usize; 9];
thread_local! { static ACTIVE: Cell<Option<Counts>> = const { Cell::new(None) }; }

pub fn record<T>(op: impl FnOnce() -> T) -> (T, Counts) {
    ACTIVE.with(|cell| assert!(cell.replace(Some([0; 9])).is_none()));
    let value = op();
    (value, ACTIVE.with(|cell| cell.take().unwrap()))
}

pub fn bump(hit: Hit) {
    add(hit, 1);
}

pub fn add(hit: Hit, n: usize) {
    ACTIVE.with(|cell| {
        if let Some(mut c) = cell.get() {
            c[hit as usize] += n;
            cell.set(Some(c));
        }
    });
}
