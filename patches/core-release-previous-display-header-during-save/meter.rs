// Single-threaded executable, no logging or allocation inside active allocator callbacks.
// Register owner bases/expected Layout once on the original validated, deserialized Header.
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::RefCell,
    sync::atomic::{AtomicU8, Ordering},
};
static STATE: AtomicU8 = AtomicU8::new(0);
struct Alloc;
#[global_allocator]
static ALLOC: Alloc = Alloc;
#[derive(Debug, Default, Clone, PartialEq)]
pub struct Report {
    pub total: [usize; 2],
    pub pack_heap: usize,
    pub pack_live: [usize; 2],
    pub page_live: [usize; 2],
    pub tool_live: [usize; 2],
    pub final_live: [usize; 2],
    pub page: [usize; 2],
    pub allocations: [usize; 2],
    pub marks: [usize; 2],
}
struct Entry {
    base: usize,
    size: usize,
    g: usize,
    alive: bool,
}
#[derive(Default)]
struct Book {
    entries: Vec<Entry>,
    result: Report,
    registered: bool,
    bad: bool,
}
thread_local! {static BOOK:RefCell<Book>=RefCell::new(Book::default());}
fn freed(p: *mut u8, n: usize) {
    if STATE.load(Ordering::Relaxed) != 2 {
        return;
    }
    BOOK.with_borrow_mut(|b| {
        if let Ok(i) = b.entries.binary_search_by_key(&(p as usize), |e| e.base) {
            let e = &mut b.entries[i];
            // First event ends this specific allocation generation; ignore reuse at the same address.
            if e.alive {
                e.alive = false;
                if n != e.size {
                    b.bad = true
                }
            }
        }
    })
}
unsafe impl GlobalAlloc for Alloc {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        freed(p, l.size());
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        let q = unsafe { System.realloc(p, l, n) };
        if !q.is_null() {
            freed(p, l.size())
        }
        q
    }
}
pub fn arm() {
    assert_eq!(STATE.load(Ordering::Relaxed), 0);
    BOOK.with_borrow_mut(|b| *b = Book::default());
    STATE.store(1, Ordering::Relaxed)
}
pub fn active() -> bool {
    STATE.load(Ordering::Relaxed) == 2
}
pub fn finish_unseen() {
    assert_eq!(STATE.swap(0, Ordering::Relaxed), 1)
}
pub fn pack_checkpoint(bytes: usize) {
    if active() {
        BOOK.with_borrow_mut(|b| {
            if b.result.pack_heap == 0 {
                b.result.pack_heap = bytes;
                b.result.pack_live = live(b);
            }
        })
    }
}
pub fn collecting() -> bool {
    STATE.load(Ordering::Relaxed) == 1
}
fn add(ptr: usize, size: usize, g: u8) {
    if size > 0 {
        BOOK.with_borrow_mut(|b| {
            b.entries.push(Entry {
                base: ptr,
                size,
                g: g as usize,
                alive: true,
            });
        });
    }
}
pub fn string(x: &String, g: u8) {
    add(x.as_ptr() as usize, x.capacity(), g)
}
pub fn vec<T>(x: &Vec<T>, g: u8) {
    add(
        x.as_ptr() as usize,
        x.capacity() * std::mem::size_of::<T>(),
        g,
    )
}
pub fn seal() {
    assert!(collecting());
    BOOK.with_borrow_mut(|b| {
        b.entries.sort_unstable_by_key(|e| e.base);
        assert!(b.entries.windows(2).all(|es| es[0].base != es[1].base));
        for e in &b.entries {
            b.result.total[e.g] += e.size;
            b.result.allocations[e.g] += 1;
        }
        b.registered = true;
    });
    STATE.store(2, Ordering::Relaxed);
}
fn live(b: &Book) -> [usize; 2] {
    let mut n = [0; 2];
    for e in &b.entries {
        if e.alive {
            n[e.g] += e.size
        }
    }
    n
}
pub fn checkpoint(k: usize, page_heap: usize, page_bytes: usize) {
    if STATE.load(Ordering::Relaxed) != 2 {
        return;
    }
    BOOK.with_borrow_mut(|b| {
        let i = k - 1;
        if b.result.marks[i] == 0 {
            let here = live(b);
            if i == 0 {
                b.result.page_live = here;
                b.result.page = [page_heap, page_bytes]
            } else {
                b.result.tool_live = here
            }
        }
        b.result.marks[i] += 1
    })
}
pub fn finish() -> Report {
    let state = STATE.swap(0, Ordering::Relaxed);
    assert_eq!(state, 2, "did not observe a validated prior header");
    BOOK.with_borrow_mut(|b| {
        assert!(b.registered && !b.bad);
        b.result.final_live = live(b);
        assert_eq!(b.result.final_live, [0, 0]);
        b.result.clone()
    })
}
