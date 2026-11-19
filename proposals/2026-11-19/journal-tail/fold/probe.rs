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
fn main() {
    use proteus_contracts::domain::{new_thread_id, HistoryCompactionReport};
    let args:Vec<usize>=std::env::args().skip(1).map(|s|s.parse().unwrap()).collect();
    let (n,batch,active,len)=(args[0],args[1],args[2],args[3]);
    let session=SessionId::from_u128(123); let thread=new_thread_id();
    let rows:Vec<_>=(0..n).map(|i|{
        let mut m = CanonicalMessage::text(MessageRole::User,"x".repeat(len));
        m.id=RecordId::from_u128(1_000_000+i as u128);m.parts[0].part_id=RecordId::from_u128(2_000_000+i as u128);m
    }).collect();
    let record=|seq:u64,kind,messages,compaction| JournalRecord{
        schema_version:JOURNAL_SCHEMA_VERSION,record_id:RecordId::from_u128(seq as u128),
        session_seq:seq,timestamp_ms:0,session_id:session,execution_id:None,thread_id:Some(thread),turn_id:None,
        entry:JournalEntry::HistoryMutated(HistoryMutated{
          previous_revision:seq-1,new_revision:seq,mutation:kind,messages,compaction,tool_results:vec![]})};
    let mut records:Vec<_>=rows.chunks(batch).enumerate().map(|(i,b)|record(i as u64+1,HistoryMutationKind::Append,b.to_vec(),None)).collect();
    if n>active {
        let mut r=HistoryCompactionReport::unchanged(n,Some("fixture".into()));r.changed=true;r.output_messages=active;
        records.push(record(records.len() as u64+1,HistoryMutationKind::Replace,rows[n-active..].to_vec(),Some(r)));
    }
    let mut validator=JournalValidationState::default();let mut seq=1;
    #[cfg(count_allocs)] let a=counter::get();
    let t=Instant::now();
    for r in black_box(&records){validator.apply_sequenced(session,r,&mut seq).unwrap();}
    let fold_ns=t.elapsed().as_nanos();
    #[cfg(count_allocs)] let b=counter::get();
    assert_eq!(validator.history_revision(),records.len() as u64);
    let storage=validator.history().as_ptr();
    let t=Instant::now();
    #[cfg(transfer)] let final_history=black_box(validator).into_history();
    #[cfg(not(transfer))] let final_history=black_box(&validator).history().to_vec();
    let finalize_ns=t.elapsed().as_nanos();
    #[cfg(count_allocs)] let c=counter::get();
    #[cfg(count_allocs)] let counts=(b.0-a.0,b.1-a.1,c.0-b.0,c.1-b.1);
    #[cfg(not(count_allocs))] let counts=(0,0,0,0);
    assert_eq!(final_history,rows[n-active..]); assert_eq!(storage==final_history.as_ptr(),cfg!(transfer));
    println!("{n},{batch},{active},{len},{fold_ns},{finalize_ns},{},{},{},{}",counts.0,counts.1,counts.2,counts.3);
}