use super::*;
use crate::{Run, Screen};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    fmt::Write as _,
    hint::black_box,
};

struct ThreadAllocator;
thread_local! {
    static ALLOC: Cell<Option<(usize,usize)>> = const { Cell::new(None) };
}
fn count(n: usize) {
    let _ = ALLOC.try_with(|a| {
        if let Some((calls, bytes)) = a.get() {
            a.set(Some((calls + 1, bytes + n)));
        }
    });
}
unsafe impl GlobalAlloc for ThreadAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        count(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        count(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, previous: Layout, n: usize) -> *mut u8 {
        count(n);
        unsafe { System.realloc(p, previous, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
}
#[global_allocator]
static COUNT: ThreadAllocator = ThreadAllocator;
fn counted(f: impl FnOnce()) -> (usize, usize) {
    ALLOC.with(|a| a.set(Some((0, 0))));
    f();
    ALLOC.with(|a| a.replace(None).unwrap())
}

include!("ownership.inc.rs");
mod paint {
    use super::*;
    include!("paint_carrier.rs");
}
fn settle_redraw(spawned: &SpawnedDisplay) {
    // Do not call Display::snapshot here: that would grant credit and send a Wake.
    wait(|| match spawned.redraw.try_recv() {
        Ok(()) => true,
        Err(async_channel::TryRecvError::Empty) => false,
        Err(e) => panic!("display closed before redraw: {e}"),
    });
    assert!(!spawned.display.shared.frame_credit.load(Ordering::Acquire));
}
fn line(id: usize) -> String {
    format!(
        "\x1b[0mrow-{id:03} 界 \x1b[1;3;4;9;38;2;1;2;3;48;2;17;33;99mexplicit\x1b[0m then default"
    )
}
#[test]
fn r91_palette_wake_and_immutable_visible_frames() {
    println!("\nARM {}", env!("R91_TERMINAL_ARM"));
    let spawned = Display::with_engine(Grid::new(96, 28), "alacritty").unwrap();
    // Consume the startup blank publication and its credit. A equals startup
    // Base; the A Wake cannot itself dirty a blank frame before our one Feed.
    settle_redraw(&spawned);
    let display = &spawned.display;
    let a = BASE;
    let b = Base { foreground: [88, 99, 110], background: [15, 22, 29] };
    let seed = display.snapshot(a);
    assert_eq!(seed.columns, 96);
    assert_eq!(seed.rows.len(), 28);
    assert!(seed.rows.iter().all(Vec::is_empty));
    drop(seed);
    let mut input = String::new();
    for row in 0..16 {
        if row != 0 { input.push_str("\r\n"); }
        write!(&mut input,"{}", line(row)).unwrap();
    }
    assert!(display.feed(input.into_bytes()));
    settle_redraw(&spawned);
    let frame_a = display.shared.view.lock().unwrap().screen.clone();
    let old = Screen::clone(&frame_a);
    assert!(old.text().contains("row-015"));
    assert_eq!(old.cursor, Some((15, 32)));
    assert_eq!(old.scrolled, 0);
    let plain = old.rows[0].iter().find(|run| run.text.contains('界')).unwrap();
    assert_eq!(plain.style.foreground,a.foreground);
    assert_eq!(plain.width, plain.text.chars().count() + 1);
    let explicit = old.rows[0].iter().find(|run| run.text.contains("explicit")).unwrap();
    assert_eq!(explicit.style.foreground,[1,2,3]);
    assert_eq!(explicit.style.background,Some([17,33,99]));
    assert!(explicit.style.bold && explicit.style.italic && explicit.style.underline && explicit.style.strike);

    assert!(spawned.redraw.is_empty());
    // Exactly one B snapshot requests a new theme and returns the old frame.
    // Nothing else calls snapshot, feed, resize, scroll, or wake until this B redraw.
    let in_flight = display.snapshot(b);
    assert_eq!(Screen::clone(&in_flight), old);
    settle_redraw(&spawned);
    let frame_b = display.shared.view.lock().unwrap().screen.clone();
    let mut expected = old.clone();
    for run in expected.rows.iter_mut().flatten() {
        if run.style.foreground == a.foreground {
            run.style.foreground=b.foreground;
        }
    }
    assert_ne!(Screen::clone(&frame_b), old);
    assert_eq!(Screen::clone(&frame_b), expected);
    assert_eq!(Screen::clone(&frame_a), old);
    assert_eq!(Screen::clone(&in_flight), old);
    println!("TRACE palette-only B: one snapshot returns A, actual redraw without further wakes, default foreground changes, explicit styled RGB and full frame otherwise unchanged");
    // The A frame and A returned by snapshot share data only in the candidate.
    assert_eq!(frame_a.rows.as_ptr()==in_flight.rows.as_ptr(),SHARED);
    assert_ne!(frame_a.rows.as_ptr(),frame_b.rows.as_ptr());
    let old_backing_a = weak(&frame_a);
    drop(frame_a);
    if let Some(a) = old_backing_a.as_ref() { assert!(a.upgrade().is_some()); }
    drop(in_flight);
    if let Some(a) = old_backing_a { assert!(a.upgrade().is_none()); }

    // B is still fresh with no feed/resize. Snapshot wakes are intentionally
    // repeated here to count real foreground handoffs, not the earlier palette test.
    const READS:usize=16;
    let runs=frame_b.rows.iter().map(Vec::len).sum::<usize>();
    let nonempty=frame_b.rows.iter().filter(|r| !r.is_empty()).count();
    let text_bytes=frame_b.rows.iter().flatten().map(|r|r.text.len()).sum::<usize>();
    let text_allocs=frame_b.rows.iter().flatten().filter(|r|!r.text.is_empty()).count();
    let per_read_copy_bytes=
        frame_b.rows.len()*std::mem::size_of::<Vec<Run>>() + runs*std::mem::size_of::<Run>() + text_bytes;
    let (calls,bytes)=counted(|| {
        for _ in 0..READS {
            let next=black_box(display.snapshot(b));
            let expected: &Screen = &frame_b; let observed: &Screen = &next; assert_eq!(expected, observed);
            assert_eq!(next.rows.as_ptr()==frame_b.rows.as_ptr(),SHARED);
            assert_eq!(next.rows[0][0].text.as_ptr()==frame_b.rows[0][0].text.as_ptr(),SHARED);
        }
    });
    let expected_counts=if SHARED { (0,0) } else {(READS*(1+nonempty+text_allocs),READS*per_read_copy_bytes)};
    assert_eq!((calls,bytes),expected_counts);
    println!("WORK reads={READS} grid=96x28 styled_runs={runs} visible_text_bytes={text_bytes} read_alloc_requests={calls} read_requested_bytes={bytes}");
    assert!(spawned.redraw.is_empty());
    println!("TRACE same palette: repeated reads keep full styled wide-glyph frame, cursor, order and scroll position");

    let old_backing_b=weak(&frame_b);
    assert!(display.feed(b"\r\nnew generation".to_vec()));
    settle_redraw(&spawned);
    let current=display.shared.view.lock().unwrap().screen.clone();
    assert!(current.text().contains("new generation"));
    assert_eq!(Screen::clone(&frame_b),expected);
    assert_ne!(frame_b.rows.as_ptr(),current.rows.as_ptr());
    if let Some(b) = old_backing_b.as_ref() { assert!(b.upgrade().is_some()); }
    drop(frame_b);
    if let Some(b) = old_backing_b { assert!(b.upgrade().is_none()); }
    assert!(spawned.input.is_empty());
    println!("TRACE new bytes publish distinct frame, old readers immutable and release after drop");
}

#[test]
fn r91_remote_cursor_is_a_render_only_projection() {
    paint::run();
}
