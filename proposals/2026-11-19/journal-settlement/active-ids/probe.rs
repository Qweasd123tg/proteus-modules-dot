use proteus_contracts::{
    domain::{RecordId, SessionId},
    model_standard::{CanonicalMessage, MessageRole},
    storage::journal::{HistoryMutated, HistoryMutationKind, JournalEntry, JournalRecord, JOURNAL_SCHEMA_VERSION},
};
use proteus_session_semantics::JournalValidationState;
use std::{hint::black_box, time::Instant};
#[cfg(count_allocs)]
mod counter {
    use std::alloc::{GlobalAlloc, Layout, System};
    use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
    pub static CALLS: AtomicU64 = AtomicU64::new(0);
    pub static BYTES: AtomicU64 = AtomicU64::new(0);
    pub struct Counter;
    #[global_allocator]
    static ALLOC: Counter = Counter;
    unsafe impl GlobalAlloc for Counter {
        unsafe fn alloc(&self, l: Layout) -> *mut u8 { CALLS.fetch_add(1,Relaxed); BYTES.fetch_add(l.size() as _,Relaxed); unsafe { System.alloc(l) } }
        unsafe fn dealloc(&self,p:*mut u8,l: Layout){unsafe{System.dealloc(p,l)}}
        unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{CALLS.fetch_add(1,Relaxed); BYTES.fetch_add(n as _,Relaxed);unsafe{System.realloc(p,l,n)}}
    }
    pub fn get()->(u64,u64){(CALLS.load(Relaxed),BYTES.load(Relaxed))}
}
fn record(i: u64, session: SessionId, text_len: usize)->JournalRecord{
    let mut m = CanonicalMessage::text(MessageRole::User, "x".repeat(text_len));
    m.id = RecordId::from_u128(10_000_000 + i as u128);
    m.parts[0].part_id = RecordId::from_u128(20_000_000 + i as u128);
    JournalRecord { schema_version:JOURNAL_SCHEMA_VERSION, record_id:RecordId::from_u128(i as u128+1), session_seq:i+1,timestamp_ms:0,session_id:session,execution_id:None,thread_id:None,turn_id:None,
    entry:JournalEntry::HistoryMutated(HistoryMutated{previous_revision:i,new_revision:i+1,mutation:HistoryMutationKind::Append,messages:vec![m],compaction:None,tool_results:vec![]}) }
}
fn main(){
    let n:usize = std::env::args().nth(1).unwrap().parse().unwrap();
    let len:usize = std::env::args().nth(2).unwrap().parse().unwrap();
    let reps:usize = std::env::args().nth(3).unwrap().parse().unwrap();
    let id=SessionId::from_u128(123);
    let records:Vec<_>=(0..n as u64).map(|i|record(i,id,len)).collect();
    for _ in 0..reps{
        let mut state=JournalValidationState::default(); let mut seq=1;
        #[cfg(count_allocs)] let a0=counter::get();
        let now=Instant::now();
        for r in black_box(&records) { state.apply_sequenced(id, r,&mut seq).unwrap(); }
        let ns=now.elapsed().as_nanos();
        #[cfg(count_allocs)] let (calls,bytes)={let a1=counter::get();(a1.0-a0.0,a1.1-a0.1)};
        #[cfg(not(count_allocs))] let (calls,bytes)= (0,0);
        assert_eq!(state.history_revision(),n as u64); assert_eq!(state.history().len(),n); assert_eq!(seq,n as u64+1);
        let history=state.into_history(); for (i,m) in history.iter().enumerate(){assert_eq!(m.id,RecordId::from_u128(10_000_000 + i as u128));}
        println!("{n} {len} {ns} {calls} {bytes}");
    }
}
