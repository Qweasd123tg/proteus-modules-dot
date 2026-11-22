use std::{borrow::Cow,cell::Cell,path::Path};
#[derive(Clone,Copy,Default,Debug,PartialEq,Eq)]
pub struct Work { pub prefixed:usize, pub borrowed:usize, pub owned:usize }
thread_local! {
    static OBSERVED:Cell<Work> = const {Cell::new(Work{prefixed:0,borrowed:0,owned:0})};
}
fn count(f:impl FnOnce(&mut Work)) { let mut work=OBSERVED.get();f(&mut work);OBSERVED.set(work); }
pub fn reset(){OBSERVED.set(Work::default());}
pub fn observed()->Work{OBSERVED.get()}
pub fn prefixed(path:&Path)->String {
    count(|w|w.prefixed+=1);
    crate::tabs::chat(path)
}
pub fn lossy_suffix(path:&Path)->Cow<'_,str> {
    let text=path.to_string_lossy();
    count(|w|match text {Cow::Borrowed(_)=>w.borrowed+=1,Cow::Owned(_)=>w.owned+=1});
    text
}
