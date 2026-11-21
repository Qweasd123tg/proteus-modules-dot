#![allow(dead_code)]
use proteus_diff::{File, FileInfo, Kind, Pair, parse};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    rc::Rc,
    sync::atomic::{AtomicBool, AtomicUsize, Ordering::Relaxed},
};

struct Counting;
static COUNT: AtomicBool = AtomicBool::new(false);
static CALLS: AtomicUsize = AtomicUsize::new(0);
static BYTES: AtomicUsize = AtomicUsize::new(0);
fn count(bytes: usize) {
    if COUNT.load(Relaxed) {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(bytes, Relaxed);
    }
}
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        count(layout.size());
        unsafe { System.alloc(layout) }
    }
    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        count(layout.size());
        unsafe { System.alloc_zeroed(layout) }
    }
    unsafe fn realloc(&self, p: *mut u8, before: Layout, n: usize) -> *mut u8 {
        count(n);
        unsafe { System.realloc(p, before, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, layout: Layout) {
        unsafe { System.dealloc(p, layout) }
    }
}
#[global_allocator]
static ALLOC: Counting = Counting;
fn counted(f: impl FnOnce()) -> (usize, usize) {
    CALLS.store(0, Relaxed);
    BYTES.store(0, Relaxed);
    COUNT.store(true, Relaxed);
    f();
    COUNT.store(false, Relaxed);
    (CALLS.load(Relaxed), BYTES.load(Relaxed))
}

struct ClipboardItem(String);
impl ClipboardItem {
    fn new_string(text: String) -> Self {
        Self(text)
    }
}
#[derive(Default)]
struct Context {
    stopped: bool,
    writes: Vec<String>,
}
impl Context {
    fn stop_propagation(&mut self) {
        self.stopped = true;
    }
    fn write_to_clipboard(&mut self, item: ClipboardItem) {
        assert!(self.stopped, "copy button must stop propagation before writing");
        self.writes.push(item.0);
    }
}
type Click = Box<dyn Fn((), (), &mut Context)>;
#[derive(Default)]
struct Button {
    disabled: bool,
    hint: &'static str,
    click: Option<Click>,
}
impl Button {
    fn disabled(mut self, disabled: bool) -> Self {
        self.disabled = disabled;
        self
    }
    fn hint(mut self, hint: &'static str, _: &mut Context) -> Self {
        self.hint = hint;
        self
    }
    fn on_click(mut self, f: impl Fn((), (), &mut Context) + 'static) -> Self {
        self.click = Some(Box::new(f));
        self
    }
    fn press(&self, cx: &mut Context) {
        cx.stopped = false;
        if !self.disabled {
            self.click.as_ref().unwrap()((), (), cx);
        }
    }
}
include!("copy.inc.rs");

fn clipboard(fixtures: Vec<File>, expected: &[&str]) {
    assert_eq!(fixtures.len(), expected.len());
    let mut cx = Context::default();
    for (file, &expected) in fixtures.into_iter().zip(expected) {
        assert_eq!(file.patch.as_str().as_bytes(), expected.as_bytes());
        let button = copy_button(Rc::new(file), &mut cx);
        let before = cx.writes.len();
        assert_eq!(button.disabled, expected.is_empty());
        assert_eq!(button.hint, "Копировать diff файла");
        button.press(&mut cx);
        assert_eq!(cx.stopped, !expected.is_empty());
        if expected.is_empty() {
            assert_eq!(cx.writes.len(), before);
        } else {
            assert_eq!(cx.writes.len(), before + 1);
            assert_eq!(cx.writes[before].as_bytes(), expected.as_bytes());
        }
    }
}

fn protocol_bytes() {
    let a = "*** Add File: src/слово.rs\r\n+alpha\r\n+é😀\r\n";
    let b = "*** Update File: src/two.rs\r\n@@\r\n-old\r\n+new";
    let wrapped = "\r\n*** Begin Patch\r\n*** Add File: src/слово.rs\r\n+alpha\r\n*** End of File\r\n+é😀\r\n*** End Patch\r\n*** Update File: src/two.rs\r\n@@\r\n-old\r\n+new";
    let files = parse(wrapped, &[]);
    assert_eq!(files[0].path, "src/слово.rs");
    assert_eq!((files[0].added, files[0].removed), (2, 0));
    assert_eq!((files[1].added, files[1].removed), (1, 1));
    clipboard(files, &[a, b]);

    let plain_a = "--- a/one\r\n+++ b/one\r\n";
    let plain_b = "--- a/two\r\n+++ b/two\r\n@@ -1 +1 @@\r\n-old\r\n+new\r\n\\ No newline at end of file";
    let plain = parse(&format!("{plain_a}{plain_b}"), &[]);
    assert_eq!((plain[0].path.as_str(), plain[1].path.as_str()), ("one", "two"));
    assert_eq!(plain[1].lines[1].old, Some(1));
    assert_eq!(plain[1].lines[2].new, Some(1));
    assert!(plain[1].lines[2].no_newline);
    clipboard(plain, &[plain_a, plain_b]);

    let bin = "diff --git a/tile.png b/tile.png\r\nnew file mode 100644\r\nindex 000..123\r\nGIT binary patch\r\nliteral 2\r\nCtest\r\n\r\nliteral 0\r\nHcmV?d00001\r\n\r\n";
    let text = "diff --git a/next.rs b/next.rs\n--- a/next.rs\n+++ b/next.rs\n@@ -1 +1 @@\n-one\n+two\n";
    let binary_and_text = parse(&format!("{bin}{text}"), &[]);
    assert_eq!(binary_and_text[0].lines[0].kind, Kind::Note);
    assert_eq!(binary_and_text[0].pairs, [Pair::Full(0)]);
    clipboard(binary_and_text, &[bin, text]);
    let info = [FileInfo {path:"absent.png".into(), status:"modified".into(), message:None}];
    clipboard(parse("", &info), &[""]);
    assert!(parse("\r\n*** Begin Patch\r\n*** End Patch", &[]).is_empty());
    println!("PASS copy bytes: CRLF, UTF-8, interior wrapper skips, no terminal LF, consecutive plain headers, Git binary block, metadata-only and empty");
}

fn old_generation() {
    let old_a = "*** Add File: same.txt\n+old first\n";
    let old_b = "*** Update File: same.txt\n@@\n-stale second\n+old second";
    let new_a = "*** Add File: renamed.txt\n+new position zero\n";
    let new_b = "*** Add File: same.txt\n+new position one";
    let mut cx = Context::default();
    let old: Vec<_> = parse(&format!("{old_a}{old_b}"), &[]).into_iter().map(Rc::new).collect();
    assert_eq!(old[0].path, old[1].path);
    let retired = old.iter().map(Rc::downgrade).collect::<Vec<_>>();
    let old_buttons = old.iter().map(|file| copy_button(Rc::clone(file), &mut cx)).collect::<Vec<_>>();
    drop(old);
    assert!(retired.iter().all(|file| file.upgrade().is_none()));

    let current = parse(&format!("{new_a}{new_b}"), &[]);
    let new_buttons = current.into_iter().map(|file| copy_button(Rc::new(file), &mut cx)).collect::<Vec<_>>();
    old_buttons[1].press(&mut cx);
    new_buttons[0].press(&mut cx);
    old_buttons[0].press(&mut cx);
    new_buttons[1].press(&mut cx);
    old_buttons[1].press(&mut cx);
    assert_eq!(cx.writes, [old_b,new_a,old_a,new_b,old_b]);
    assert_ne!(cx.writes[0].as_ptr(), cx.writes[4].as_ptr());
    println!("PASS old and new copy callbacks preserve exact generation and duplicate-path file order without retaining parsed File; repeat clicks own separate clipboard strings");
}

fn work() {
    // One moderate source patch rather than a huge-body stress loop. Other
    // layout, parser and clipboard allocations are deliberately outside this interval.
    let title = "*** Add File: src/report.txt\n";
    let mut raw = title.to_owned();
    for i in 0..640 {
        use std::fmt::Write;
        writeln!(&mut raw,"+entry {i:03} | yesterday: planned; today: reviewed; result: ready for next stage").unwrap();
    }
    let file = Rc::new(parse(&raw,&[]).pop().unwrap());
    assert_eq!(file.lines.len(), 640);
    assert_eq!(file.patch.as_str(),raw);
    let bytes_per_payload=file.patch.as_str().len();
    let mut cx=Context::default();
    const REBUILDS:usize=12;
    let (calls,bytes) = counted(|| {
        for _ in 0..REBUILDS {
            let button = std::hint::black_box(copy_button(Rc::clone(&file),&mut cx));
            assert!(!button.disabled);
        }
    });
    let shared = cfg_shared(file.as_ref());
    let capture=if shared {std::mem::size_of::<usize>()} else {std::mem::size_of::<String>()};
    assert_eq!(calls, REBUILDS * if shared {1} else {2});
    assert_eq!(bytes, REBUILDS * (capture + if shared {0} else {bytes_per_payload}));
    eprintln!("WORK header_rebuilds={REBUILDS} file_patch_bytes={bytes_per_payload} raw_snapshot_copy_bytes={} handoff_alloc_requests={calls} handoff_requested_bytes={bytes}", if shared {0} else {REBUILDS*bytes_per_payload});
    let prepared=copy_button(file,&mut cx);
    prepared.press(&mut cx);
    assert_eq!(cx.writes[0], raw);
    println!("PASS unchanged rich file header copy bytes across rebuild and click");
}

fn main() {
    eprintln!("ARM {}",env!("R89_DIFF_PROBE_ARM"));
    protocol_bytes();
    old_generation();
    work();
}
