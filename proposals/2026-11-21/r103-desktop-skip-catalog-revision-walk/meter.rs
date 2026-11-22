use std::cell::Cell;

#[derive(Clone, Copy)]
#[repr(usize)]
pub enum Hit {
    DiscoveryRoot,
    ManifestLoad,
    InstructionRoot,
    InstructionDir,
    InstructionFile,
    Revision,
    RevisionDir,
    RevisionMetadata,
}

type Counts = [usize; 8];
thread_local! { static ACTIVE: Cell<Option<Counts>> = const { Cell::new(None) }; }

pub fn record<T>(op: impl FnOnce() -> T) -> (T, Counts) {
    ACTIVE.with(|cell| assert!(cell.replace(Some([0; 8])).is_none()));
    let ret = op();
    let counts = ACTIVE.with(|cell| cell.take().unwrap());
    (ret, counts)
}

pub fn bump(hit: Hit) {
    ACTIVE.with(|cell| {
        if let Some(mut record) = cell.get() {
            record[hit as usize] += 1;
            cell.set(Some(record));
        }
    });
}

pub fn print(label: &str, counts: Counts) {
    eprintln!("WORK {label}: {:?}", counts);
}
