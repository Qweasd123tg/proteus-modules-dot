use std::collections::HashMap;
use std::cell::RefCell;
#[derive(Default)]
struct Cache {
    pub(crate) prunes: usize,
    pub(crate) retired: usize,
}
impl Cache {
    fn prune(&mut self) {
        self.prunes += 1;
        self.retired = 0;
    }
}
#[derive(Default)]
struct Shared { cache: Cache }
thread_local! { static SHARED: RefCell<Shared> = RefCell::default(); }

#[derive(Default)]
pub(crate) struct SentImages { pub(crate) by_id: HashMap<String,u64> }
pub(crate) fn shared() -> (usize,usize) {
    SHARED.with(|slot| (slot.borrow().cache.prunes,slot.borrow().cache.retired))
}
pub(crate) fn stage_retired() { SHARED.with(|slot| slot.borrow_mut().cache.retired = 7); }
