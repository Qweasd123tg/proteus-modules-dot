// Framing-only comparison of the std::io paths, not a runtime speed benchmark.
use std::{
    alloc::{GlobalAlloc, Layout, System},
    fs::File,
    hash::{DefaultHasher, Hasher},
    io::{self, BufRead, BufReader, Read},
    sync::atomic::{AtomicUsize, Ordering::Relaxed},
};

struct Counts;
static ALLOCS: AtomicUsize = AtomicUsize::new(0);
static REALLOCS: AtomicUsize = AtomicUsize::new(0);
static REQUESTED: AtomicUsize = AtomicUsize::new(0);

unsafe impl GlobalAlloc for Counts {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Relaxed);
        REQUESTED.fetch_add(layout.size(), Relaxed);
        unsafe { System.alloc(layout) }
    }
    unsafe fn realloc(&self, ptr: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        REALLOCS.fetch_add(1, Relaxed);
        REQUESTED.fetch_add(new_size, Relaxed);
        unsafe { System.realloc(ptr, layout, new_size) }
    }
    unsafe fn dealloc(&self, ptr: *mut u8, layout: Layout) {
        unsafe { System.dealloc(ptr, layout) }
    }
}

#[global_allocator]
static A: Counts = Counts;
const BUF: usize = 64 * 1024;
const LINE_LIMIT: usize = 128 * 1024 * 1024;

fn observe<R: Read>(r: R, n: u64, candidate: bool) -> io::Result<((usize, u64), [usize; 4])> {
    let mut reader = BufReader::with_capacity(BUF, r.take(n));
    let mut hasher = DefaultHasher::new();
    let (mut count, mut borrowed) = (0, 0);
    let mut consume = |line: &[u8]| {
        assert!(line.ends_with(b"\n") && line.len() <= LINE_LIMIT);
        hasher.write_usize(line.len());
        hasher.write(line);
        count += 1;
    };
    let before = [
        ALLOCS.load(Relaxed),
        REALLOCS.load(Relaxed),
        REQUESTED.load(Relaxed),
    ];
    loop {
        if candidate {
            match reader.fill_buf() {
                Ok(bytes) => {
                    if let Some(end) = memchr::memchr(b'\n', bytes)
                        && end < LINE_LIMIT
                    {
                        consume(&bytes[..=end]);
                        reader.consume(end + 1);
                        borrowed += 1;
                        continue;
                    }
                }
                Err(err) if err.kind() == io::ErrorKind::Interrupted => {}
                Err(err) => return Err(err),
            }
        }
        let mut line = Vec::new();
        if reader
            .by_ref()
            .take((LINE_LIMIT + 1) as u64)
            .read_until(b'\n', &mut line)?
            == 0
        {
            break;
        }
        consume(&line);
    }
    Ok((
        (count, hasher.finish()),
        [
            borrowed,
            ALLOCS.load(Relaxed) - before[0],
            REALLOCS.load(Relaxed) - before[1],
            REQUESTED.load(Relaxed) - before[2],
        ],
    ))
}

#[derive(Clone)]
struct OnceInterrupted<T>(T, bool);
impl<T: Read> Read for OnceInterrupted<T> {
    fn read(&mut self, bytes: &mut [u8]) -> io::Result<usize> {
        if std::mem::replace(&mut self.1, false) {
            return Err(io::ErrorKind::Interrupted.into());
        }
        self.0.read(bytes)
    }
}

fn compare<R: Read>(name: &str, new: impl Fn() -> R, n: u64) {
    let stock = observe(new(), n, false).unwrap();
    let cand = observe(new(), n, true).unwrap();
    assert_eq!(stock.0, cand.0);
    println!(
        "{name}: {} lines; {} borrowed; stock alloc/realloc/requested_bytes={:?}, candidate={:?}",
        stock.0.0,
        cand.1[0],
        &stock.1[1..],
        &cand.1[1..]
    );
}

fn main() {
    let j = std::env::args().nth(1).unwrap();
    let len = File::open(&j).unwrap().metadata().unwrap().len();
    compare("R35 mixed56 synthetic", || File::open(&j).unwrap(), len);
    for (name, sizes, reps) in [
        ("small", vec![8, 13, 389], 4000),
        ("over-buffer then small", vec![190_000, 8, 13], 30),
        ("all straddling", vec![75_000, 125_000], 64),
        ("one buffer and one byte", vec![65_536, 65_537], 20),
    ] {
        let mut input = Vec::new();
        for _ in 0..reps {
            for l in &sizes {
                input.resize(input.len() + l - 1, b'x');
                input.push(b'\n');
            }
        }
        compare(name, || &input[..], input.len() as u64);
    }
    let input = b"sample framed bytes\nnext framed bytes\n";
    compare(
        "interrupted initial fill",
        || OnceInterrupted(&input[..], true),
        input.len() as u64,
    );
}
