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
    ModuleDir,
    InventoryManifestMeta,
    InventoryManifestRead,
    InventoryProgramCheck,
    ProviderManifestMeta,
    ProviderManifestRead,
    ProviderProgramOpen,
    ProviderHashBytes,
}

type Counts = [usize; 16];
thread_local! { static ACTIVE: Cell<Option<Counts>> = const { Cell::new(None) }; }

pub fn record<T>(op: impl FnOnce() -> T) -> (T, Counts) {
    ACTIVE.with(|cell| assert!(cell.replace(Some([0; 16])).is_none()));
    let ret = op();
    let counts = ACTIVE.with(|cell| cell.take().unwrap());
    (ret, counts)
}

pub fn bump(hit: Hit) {
    add(hit, 1);
}

pub fn add(hit: Hit, amount: usize) {
    ACTIVE.with(|cell| {
        if let Some(mut record) = cell.get() {
            record[hit as usize] += amount;
            cell.set(Some(record));
        }
    });
}

pub fn print(label: &str, counts: Counts) {
    eprintln!("WORK {label}: {:?}", counts);
}
