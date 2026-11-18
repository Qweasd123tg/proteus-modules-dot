// Test-only allocation traffic probe. Append this module to
// crates/proteus-core/src/core/session_store/remote/view/tests.rs in both trees.
mod allocation_probe {
    use super::{Backend, RemoteValidatedRead};
    use proteus_contracts::model_standard::ContentPart;
    use proteus_contracts::storage::journal::JournalEntry;
    use std::{
        alloc::{GlobalAlloc, Layout, System},
        hint::black_box,
        sync::atomic::{AtomicBool, AtomicIsize, AtomicUsize, Ordering::Relaxed},
        time::Instant,
    };

    struct Traffic;
    #[global_allocator]
    static ALLOCATOR: Traffic = Traffic;
    static ACTIVE: AtomicBool = AtomicBool::new(false);
    static BYTES: AtomicUsize = AtomicUsize::new(0);
    static COUNT: AtomicUsize = AtomicUsize::new(0);
    static NET: AtomicIsize = AtomicIsize::new(0);
    static HIGH: AtomicIsize = AtomicIsize::new(0);
    fn net(delta: isize) {
        let now = NET.fetch_add(delta, Relaxed) + delta;
        HIGH.fetch_max(now, Relaxed);
    }
    fn account(size: usize, old_size: usize) {
        if ACTIVE.load(Relaxed) {
            BYTES.fetch_add(size, Relaxed);
            COUNT.fetch_add(1, Relaxed);
            net(size as isize - old_size as isize);
        }
    }
    // Each operation is forwarded to System with the original layout. Count
    // cumulative requests and peak live requested bytes above entry, net of frees.
    // Reallocation contributes its new size to traffic and its difference to live bytes.
    // Neither measure includes allocator overhead, RSS, or internal realloc copying.
    unsafe impl GlobalAlloc for Traffic {
        unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
            account(layout.size(), 0);
            unsafe { System.alloc(layout) }
        }
        unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
            account(layout.size(), 0);
            unsafe { System.alloc_zeroed(layout) }
        }
        unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
            if ACTIVE.load(Relaxed) {
                net(-(layout.size() as isize));
            }
            unsafe { System.dealloc(ptr, layout) }
        }
        unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, size: usize) -> *mut u8 {
            account(size, layout.size());
            unsafe { System.realloc(ptr, layout, size) }
        }
    }

    #[test]
    fn reject_mismatched_revision_after_scanning_records() {
        use proteus_contracts::{
            domain::{AgentTask, new_execution_id, new_turn_id},
            storage::journal::TurnOpened,
        };
        let (backend, store) = Backend::store();
        backend.append(1);
        {
            let mut state = backend.0.lock().unwrap();
            let record = &mut state.records[0];
            record.turn_id = Some(new_turn_id());
            record.execution_id = Some(new_execution_id());
            // The fixture advertises revision 1 for one record; a TurnOpened
            // has a valid zero base and does not itself increment that revision.
            record.entry = JournalEntry::TurnOpened(TurnOpened {
                intent: None,
                task: AgentTask::new("allocation fixture", "/workspace".into()),
                base_history_revision: 0,
                module_epoch: 0,
                config_snapshot: serde_json::json!({}),
            });
        }
        let err = RemoteValidatedRead::open(store).err().expect("revision mismatch");
        assert_eq!(err.to_string(), "storage snapshot history revision mismatch");
        assert_eq!(backend.0.lock().unwrap().record_reads, 1);
    }

    #[test]
    #[ignore = "Synthetic allocation measurement; run alone, one test thread"]
    fn measure_validated_remote_open() {
        for (n, bytes, per_record) in [(0, 0, 1), (256, 64 * 1024, 256), (256, 64 * 1024, 1)] {
            let (backend, store) = Backend::store();
            if n > 0 {
                for _ in 0..n / per_record {
                    backend.append(per_record);
                }
                let mut state = backend.0.lock().unwrap();
                for (record_index, record) in state.records.iter_mut().enumerate() {
                    record.record_id = uuid::Uuid::from_u128(record_index as u128 + 1000);
                    record.thread_id = Some(uuid::Uuid::from_u128(7));
                    let JournalEntry::HistoryMutated(entry) = &mut record.entry else {
                        panic!("fixture history")
                    };
                    for (index, msg) in entry.messages.iter_mut().enumerate() {
                        let id = record_index * per_record + index;
                        msg.id = uuid::Uuid::from_u128(id as u128 + 2000);
                        msg.parts[0].part_id = uuid::Uuid::from_u128(id as u128 + 3000);
                        let ContentPart::Text { text } = &mut msg.parts[0].payload else {
                            panic!("fixture text")
                        };
                        *text = char::from(b'A' + (id % 26) as u8).to_string().repeat(bytes);
                    }
                }
            }
            for rep in 0..8 {
                COUNT.store(0, Relaxed);
                NET.store(0, Relaxed);
                HIGH.store(0, Relaxed);
                BYTES.store(0, Relaxed);
                let now = Instant::now();
                ACTIVE.store(true, Relaxed);
                let read = black_box(RemoteValidatedRead::open(store.clone()).unwrap());
                ACTIVE.store(false, Relaxed);
                let micros = now.elapsed().as_micros();
                let allocs = COUNT.load(Relaxed);
                let peak_above_entry = HIGH.load(Relaxed);
                let requested = BYTES.load(Relaxed);
                let state = backend.0.lock().unwrap();
                let rows = read.history();
                assert_eq!(rows.len(), n);
                assert!(rows.iter().eq(state.records.iter().flat_map(|record| {
                    let JournalEntry::HistoryMutated(entry) = &record.entry else {
                        panic!("fixture history")
                    };
                    &entry.messages
                })));
                drop(state);
                drop(read);
                println!("PROBE n={n} size={bytes} per_record={per_record} rep={rep} calls={allocs} bytes={requested} peak_extra={peak_above_entry} micros={micros}");
            }
        }
    }
}
