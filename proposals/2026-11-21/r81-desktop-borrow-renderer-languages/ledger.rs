use std::cell::Cell;
thread_local! {
    static CLONED_NAMES:Cell<usize>=const {Cell::new(0)};
    static YIELDED_NAMES:Cell<usize>=const {Cell::new(0)};
}
pub fn yielded(){YIELDED_NAMES.set(YIELDED_NAMES.get()+1);}
pub fn clone_name(name:&String)->String{
    CLONED_NAMES.set(CLONED_NAMES.get()+1);
    yielded();
    name.clone()
}
pub fn reset(){CLONED_NAMES.set(0);YIELDED_NAMES.set(0);}
pub fn counts()->(usize,usize){(CLONED_NAMES.get(),YIELDED_NAMES.get())}
