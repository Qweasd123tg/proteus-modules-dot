use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};

use alacritty_terminal::event::VoidListener;
use alacritty_terminal::grid::{Dimensions, Scroll};
use alacritty_terminal::term::{Config, Term};
use alacritty_terminal::vte::ansi::Processor;

mod candidate;
mod screen;
mod stock;
use screen::{Base, Screen};

struct Counting;
static CALLS: AtomicU64 = AtomicU64::new(0);
static BYTES: AtomicU64 = AtomicU64::new(0);
#[global_allocator]
static ALLOC: Counting = Counting;

unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(l.size() as u64, Relaxed);
        unsafe { System.alloc(l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(l.size() as u64, Relaxed);
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        CALLS.fetch_add(1, Relaxed);
        BYTES.fetch_add(n as u64, Relaxed);
        unsafe { System.realloc(p, l, n) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
}
#[derive(Clone, Copy)]
struct Size(usize, usize);
impl Dimensions for Size {
    fn total_lines(&self) -> usize {
        self.1
    }
    fn screen_lines(&self) -> usize {
        self.1
    }
    fn columns(&self) -> usize {
        self.0
    }
}

const DARK: Base = Base {
    foreground: [200, 220, 240],
    background: [1, 2, 3],
};
const LIGHT: Base = Base {
    foreground: [1, 4, 7],
    background: [250, 251, 252],
};
fn rng(s: &mut u64) -> usize {
    *s = s
        .wrapping_mul(6364136223846793005)
        .wrapping_add(1442695040888963407);
    (*s >> 32) as usize
}
fn parity() -> usize {
    let tokens: &[&[u8]] = &[
        b"a",
        "Пр".as_bytes(),
        "e\u{301}\u{308}".as_bytes(),
        "界".as_bytes(),
        "🙂".as_bytes(),
        b" ",
        b"  ",
        b"\t",
        b"\x08",
        b"\r\n",
        b"\r",
        b"\x1b[0m",
        b"\x1b[31;1m",
        b"\x1b[4;2m",
        b"\x1b[48;2;3;7;11m",
        b"\x1b[8m",
        b"\x1b[9m",
        b"\x1b[7m",
        b"\x1b[?25l",
        b"\x1b[?25h",
        b"\x1b[?1049h",
        b"\x1b[?1049l",
        b"\x1b[H",
        b"\x1b[2K",
        b"\x1b[1;3H",
        b"\x1b[3B",
        b"\x1b[2A",
        b"\x1b[2D",
        b"\x1b[38;5;201m",
        b"\x1b[3m",
        b"\x1b[4:3m",
        b"\x1b[22;23;24;27;28;29;39;49m",
        b"\x1b[38;2;1;",
        b"2;3m",
        b"\xf0\x9f",
        b"\x99\x82",
        b"\xff",
        b"\x1b[2J",
    ];
    let mut n = 0;
    for seed in 1..=8 {
        let mut s = seed;
        let size = Size(2 + rng(&mut s) % 35, 1 + rng(&mut s) % 11);
        let mut t = Term::new(Config::default(), &size, VoidListener);
        let mut p: Processor = Processor::new();
        for _ in 0..320 {
            match rng(&mut s) % 29 {
                0 => t.resize(Size(2 + rng(&mut s) % 35, 1 + rng(&mut s) % 11)),
                1 => t.scroll_display(Scroll::Delta(1 + (rng(&mut s) % 9) as i32)),
                2 => t.scroll_display(Scroll::Bottom),
                _ => {
                    for _ in 0..1 + rng(&mut s) % 9 {
                        let bytes = tokens[rng(&mut s) % tokens.len()];
                        p.advance(&mut t, bytes);
                    }
                }
            }
            for base in [DARK, LIGHT] {
                assert_eq!(
                    stock::snapshot(&t, base),
                    candidate::snapshot(&t, base),
                    "transition {n}"
                );
                n += 1;
            }
        }
    }
    n
}

fn counters() -> (u64, u64) {
    (CALLS.load(Relaxed), BYTES.load(Relaxed))
}
fn measure(make: impl FnOnce() -> Screen) -> (Screen, u64, u64) {
    let (a, b) = counters();
    let screen = std::hint::black_box(make());
    let (c, d) = counters();
    (screen, c - a, d - b)
}

fn matrix() {
    let columns = 120;
    let rows = 40;
    println!(
        "fixture,columns,rows,visible_runs,stock_requests,candidate_requests,stock_requested_bytes,candidate_requested_bytes"
    );
    for label in [
        "blank",
        "ascii",
        "striped",
        "alternating",
        "mixed_unicode",
        "styled_blanks",
        "scrollback",
    ] {
        let mut t = Term::new(Config::default(), &Size(columns, rows), VoidListener);
        let mut p: Processor = Processor::new();
        let mut input = String::new();
        if label == "scrollback" {
            for i in 0..rows * 6 {
                input.push_str(&format!("\x1b[34mline {i:04} \x1b[0mПривет界🙂\r\n"));
            }
        } else if label != "blank" {
            for y in 0..rows {
                input.push_str(&format!("\x1b[{};1H", y + 1));
                match label {
                    "ascii" => input.push_str(&"x".repeat(columns)),
                    "mixed_unicode" => input.push_str(&"яe\u{301}界🙂".repeat(columns / 6)),
                    "styled_blanks" => {
                        input.push_str("\x1b[4;44m");
                        input.push_str(&" ".repeat(columns));
                        input.push_str("\x1b[0m");
                    }
                    "striped" | "alternating" => {
                        for x in 0..columns {
                            let step = if label == "striped" { 12 } else { 1 };
                            if x % step == 0 {
                                input.push_str(if (x / step) % 2 == 0 {
                                    "\x1b[31m"
                                } else {
                                    "\x1b[32m"
                                });
                            }
                            input.push('x');
                        }
                    }
                    _ => unreachable!(),
                }
            }
        }
        p.advance(&mut t, input.as_bytes());
        if label == "scrollback" {
            t.scroll_display(Scroll::Delta(50));
        }
        let (a, ac, ab) = measure(|| stock::snapshot(&t, DARK));
        let (b, bc, bb) = measure(|| candidate::snapshot(&t, DARK));
        assert_eq!(a, b, "{label}");
        let r = a.rows.iter().map(Vec::len).sum::<usize>();
        if label == "alternating" {
            assert_eq!(r, columns * rows);
            assert_eq!((ac, ab), (bc, bb));
        }
        if matches!(label, "ascii" | "blank") {
            assert!(ac - bc >= ((columns - 1) * rows) as u64);
        }
        println!("{label},{columns},{rows},{r},{ac},{bc},{ab},{bb}");
    }
}
fn main() {
    println!("exact_screen_comparisons={}", parity());
    matrix();
}
