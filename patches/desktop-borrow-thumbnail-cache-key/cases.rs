#![allow(dead_code)]
extern crate self as gpui_kit;

use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Weak};

pub struct App;
type SharedString = String;

pub mod ui {
    pub mod render_image {
        use crate::App;
        pub struct Bitmap(bool);
        impl Bitmap {
            pub fn new(has_scene_lease: bool, _: Option<&App>) -> std::sync::Arc<Self> {
                std::sync::Arc::new(Self(has_scene_lease))
            }
            pub fn has_scene_lease(&self) -> bool { self.0 }
        }
    }
}

mod decode {
    pub struct Preview {
        pub image: bool,
        pub pixels: u64,
    }
}

struct ImageRef {
    id: String,
    name: String,
    mime_type: String,
    path: PathBuf,
}

mod transcript {
    pub(crate) struct Entry {
        pub(crate) images: Vec<crate::ImageRef>,
    }
}

mod harness {
use super::*;

#[derive(Default)]
struct Shared {
    cache: cache::Cache,
}

mod cache {
// @LRU@
}

// @OWNERS@
// @SENT_IMAGES@
// @UPSTREAM_TESTS@

thread_local! {
    static ALLOC: Cell<Option<(usize, usize)>> = const { Cell::new(None) };
}
struct Allocator;

fn account(size: usize) {
    let _ = ALLOC.try_with(|state| {
        if let Some((count, bytes)) = state.get() {
            state.set(Some((count + 1, bytes + size)));
        }
    });
}

unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        account(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        account(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, size: usize) -> *mut u8 {
        account(size);
        unsafe { System.realloc(pointer, layout, size) }
    }
    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        unsafe { System.dealloc(pointer, layout) }
    }
}

#[global_allocator]
static GLOBAL: Allocator = Allocator;

fn tracked<R>(call: impl FnOnce() -> R) -> (R, (usize, usize)) {
    ALLOC.with(|state| assert_eq!(state.replace(Some((0, 0))), None));
    let answer = call();
    let counts = ALLOC.with(|state| state.replace(None).unwrap());
    (answer, counts)
}

const HALF_PIXELS: u64 = 8 * 1024 * 1024;

fn reset() {
    SHARED.with(|shared| *shared.borrow_mut() = Shared::default());
}

fn keep_bitmap(key: &Key, owner: &Arc<()>, scene: bool) -> Arc<cache::Bitmap> {
    let preview = decode::Preview { image: scene, pixels: HALF_PIXELS };
    SHARED.with(|shared| shared.borrow_mut().cache.insert(key.clone(), preview, owner, None))
}

fn get_bitmap(key: &Key, owner: &Arc<()>) -> Option<Arc<cache::Bitmap>> {
    SHARED.with(|shared| shared.borrow_mut().cache.get(key, owner))
}

fn key(id: &str, p: &Path) -> Key {
    Key { connection: 41, dir: p.to_owned(), id: id.into(), edge: 96 }
}

fn populate(slot_key: Key, label: &str, state: Stored, owner: Arc<()>) -> SentImages {
    let mut images = SentImages::default();
    images.by_id.insert(label.into(), Slot {
        key: slot_key, ticket: 101, owner, rearm_on_failure: false, state,
    });
    images
}

fn borrowed_path_and_lru(local: &Path, incoming: &Path) {
    reset();
    assert_ne!(local.as_os_str(), incoming.as_os_str());
    assert_eq!(local, incoming);
    let incoming_key = key("promoted", incoming);
    let local_key = key("promoted", local);
    let other_key = key("unpromoted", local);
    let new_key = key("new", local);
    let shared_owner = Arc::new(());
    let old = keep_bitmap(&incoming_key, &shared_owner, false);
    let old_other = keep_bitmap(&other_key, &shared_owner, false);
    let mut images = populate(local_key.clone(), &local_key.id, Stored::Waiting, Arc::new(()));
    let owned = Arc::downgrade(&images.by_id[&local_key.id].owner);
    let req = reference(&local_key.id);

    assert!(images.missing(&[req], 41, incoming, 96).is_empty());
    assert!(Weak::ptr_eq(&owned, &Arc::downgrade(&images.by_id[&local_key.id].owner)));
    match &images.by_id[&local_key.id].state {
        Stored::Ready(weak) => assert!(Arc::ptr_eq(&old, &weak.upgrade().unwrap())),
        _ => panic!("equal stored slot must reuse live cache bitmap"),
    }
    // Releasing the original cache owner must not evict the adopted bitmap.
    // Two entries fill the cache; first lookup promoted our bitmap.
    let new_owner = Arc::new(());
    let _new = keep_bitmap(&new_key, &new_owner, false);
    assert!(get_bitmap(&other_key, &shared_owner).is_none());
    assert!(!Arc::ptr_eq(&old, &old_other));
    drop(shared_owner);
    assert!(Arc::ptr_eq(&old, &get_bitmap(&incoming_key, &new_owner).unwrap()));
    assert_eq!(images.by_id[&local_key.id].ticket, 101);
}

fn stale_mismatches() {
    let dir = Path::new("base/nested");
    let request = "same-map-key";
    let wrong = [
        Key { connection: 42, ..key(request, dir) },
        Key { edge: 192, ..key(request, dir) },
        key("inconsistent-stored-id", dir),
        key(request, Path::new("base/./another")),
        key(request, Path::new("base/extra/../nested")),
        key(request, Path::new("./base/nested")),
    ];
    for stale in wrong {
        stale_lookup(stale, request, dir);
    }
    #[cfg(unix)]
    {
        use std::os::unix::ffi::OsStrExt as _;
        let a = Path::new(std::ffi::OsStr::from_bytes(b"packed\xFF//./data/"));
        let b = Path::new(std::ffi::OsStr::from_bytes(b"packed\xFF/data"));
        borrowed_path_and_lru(a, b);
        let invalid = Path::new(std::ffi::OsStr::from_bytes(b"packed\xFE/data"));
        stale_lookup(key(request, invalid), request, b);
    }
}

fn stale_lookup(stale: Key, id: &str, dir: &Path) {
    reset();
    let owner = Arc::new(());
    let weak = Arc::downgrade(&owner);
    let bitmap = keep_bitmap(&stale, &owner, false);
    let mut images = populate(stale.clone(), id, Stored::Ready(Arc::downgrade(&bitmap)), owner);
    images.rearm_after_reconnect();
    assert_eq!(images.missing(&[reference(id), reference(id)], 41, dir, 96), [id, id]);
    assert!(!images.by_id.contains_key(id));
    assert!(weak.upgrade().is_none());
    assert!(get_bitmap(&stale, &Arc::new(())).is_none(), "stale owner pruned");
    assert!(Arc::strong_count(&bitmap) > 0, "test keeps old scene allocation distinguishable");
}

fn no_slot_still_reports_direct_demand() {
    reset();
    let dir = Path::new("session");
    let already_cached = key("no-slot-id", dir);
    let other = key("seed-other", dir);
    let new = key("new-after-missing", dir);
    let owner = Arc::new(());
    let _cached = keep_bitmap(&already_cached, &owner, false);
    let _other = keep_bitmap(&other, &owner, false);
    let mut images = SentImages::default();
    assert_eq!(images.missing(&[reference(&already_cached.id)], 41, dir, 96), [already_cached.id.as_str()]);
    let _fresh = keep_bitmap(&new, &owner, false);
    assert!(get_bitmap(&already_cached, &owner).is_none(), "absent slot must not touch/promote a raw cache hit");
    assert!(get_bitmap(&other, &owner).is_some());
    assert!(images.by_id.is_empty());
}

fn leases_and_retry() {
    reset();
    let dir = Path::new("ready");
    let id = "scene-id";
    for leased in [false, true] {
        reset();
        let outside = cache::Bitmap::new(leased, None);
        let stored = Stored::Ready(Arc::downgrade(&outside));
        let mut images = populate(key(id, dir), id, stored, Arc::new(()));
        let out = images.missing(&[reference(id), reference(id)], 41, dir, 96);
        let slot = &images.by_id[id];
        if leased {
            assert!(out.is_empty());
            assert!(matches!(slot.state, Stored::Ready(_)));
        } else {
            assert_eq!(out, [id]);
            assert!(matches!(slot.state, Stored::Loading));
        }
        assert_eq!(slot.ticket, 101);
    }

    for state in [Stored::Ready(Weak::new()), Stored::Waiting, Stored::Loading, Stored::Failed("error".into())] {
        let requests_once = matches!(&state, Stored::Ready(_) | Stored::Waiting);
        let remains_failed = matches!(&state, Stored::Failed(_));
        let mut images = populate(key(id, dir), id, state, Arc::new(()));
        let out = images.missing(&[reference(id), reference(id)], 41, dir, 96);
        assert_eq!(out.len(), usize::from(requests_once));
        assert_eq!(matches!(&images.by_id[id].state, Stored::Failed(_)), remains_failed);
        assert_eq!(matches!(&images.by_id[id].state, Stored::Loading), !remains_failed);
        assert_eq!(images.by_id[id].ticket, 101);
    }
    let mut images = populate(key(id, dir), id, Stored::Loading, Arc::new(()));
    // Each demand would be missing except the outstanding same key/ticket.
    images.rearm_after_reconnect();
    assert!(images.missing(&[reference(id)], 41, dir, 96).is_empty());
    assert!(images.by_id[id].rearm_on_failure);
    assert!(images.by_id[id].matches(&key(id, dir), 101));
    assert!(!images.by_id[id].matches(&key(id, dir), 102));
}

fn allocation_witness(mode: &str) {
    let dir = Path::new("workspace/long-project/retained-sessions/session-001");
    let id = "fixture-thumbnail-example-token-001";
    let request = vec![reference(id)];
    let owned = key(id, dir);
    let expected = dir.as_os_str().len() + id.len();
    let iterations = 64;
    let mut images = populate(owned.clone(), id, Stored::Waiting, Arc::new(()));
    let bitmap = keep_bitmap(&owned, &images.by_id[id].owner, false);
    let ((), (calls, bytes)) = tracked(|| {
        for _ in 0..iterations {
            let result = std::hint::black_box(images.missing(&request, 41, dir, 96));
            assert!(result.is_empty());
        }
    });
    assert!(matches!(&images.by_id[id].state, Stored::Ready(weak) if Arc::ptr_eq(&bitmap, &weak.upgrade().unwrap())));
    let old = mode == "stock";
    assert_eq!((calls, bytes), if old { (2 * iterations, expected * iterations) } else { (0, 0) });
    println!("alloc hit {calls} {bytes}");

    reset();
    let mut miss = SentImages::default();
    let (result, (calls, bytes)) = tracked(|| std::hint::black_box(miss.missing(&request, 41, dir, 96)));
    assert_eq!(result, [id]);
    // Mandatory returned ID and Vec are still present. Vec push uses the
    // standard library's pre-reserved minimum of four for String.
    let fixed = id.len() + 4 * std::mem::size_of::<String>();
    assert_eq!((calls, bytes), if old { (4, fixed + expected) } else { (2, fixed) });
    println!("alloc no-slot {calls} {bytes}");
}

pub(super) fn run_cases() {
    let mode = std::env::args().nth(1).expect("mode");
    assert!(matches!(mode.as_str(), "stock" | "post"));
    stale_completion_cannot_replace_a_rerequest_with_same_image_id();
    failure_before_reconnect_is_rearmed_only_for_the_next_demanded_render();
    failure_after_reconnect_consumes_one_coalesced_rearm_not_a_retry_loop();
    a_successful_pre_reconnect_attempt_is_kept_and_clears_its_retry_credit();
    rearming_preserves_ready_waiting_and_current_attempt_identity();
    borrowed_path_and_lru(Path::new("base//./nested/"), Path::new("base/nested"));
    stale_mismatches();
    no_slot_still_reports_direct_demand();
    leases_and_retry();
    reset();
    println!("pass path, stale ownership and ticket, hit/LRU/adoption, no-slot and duplicates, scene lease, retry");
    allocation_witness(&mode);
}
}

fn main() { harness::run_cases(); }
