#![allow(dead_code)]
#[path = "src/ui/chat/scroller/scrollbar/height_map.rs"]
mod height_map;
use height_map::HeightMap;
use std::hint::black_box;
use std::time::Instant;
struct Resident {
    heights: Vec<Option<f32>>,
    prefix: Vec<f64>,
    resident_delta: f64,
    estimate: f32,
}
struct Range { start: usize }
impl Resident {
    fn rebuild(&mut self, map: &HeightMap, range: Range) {
        include!("kernel.rs");
    }
}
fn main() {
    // No UI, I/O, map construction or allocation of the prefix in the timed loop.
    for (scenario, total, data, width, start) in [
        ("one-span", 1_000_000, 0, 200, 733_000),
        ("fragmented", 16_384, 8192, 200, 4096),
        ("page", 16_384, 8192, 50, 4096),
        ("singleton", 16_384, 8192, 1, 4096),
        ("past-end", 16, 8, 50, 14),
    ] {
        let mut map = HeightMap::with_limit(total, 80., 16_384);
        for row in 0..data {
            assert!(map.set_limited(row, [0., 34., 153.][row % 3], 16_384, 0..0));
        }
        let mut model = Resident {
            heights: (0..width).map(|i| if i % 3 == 0 { Some((i % 67) as f32) } else { None }).collect(),
            prefix: Vec::with_capacity(width + 1),
            resident_delta: 0.,
            estimate: 55.,
        };
        let reps = 128;
        let mut times = Vec::new();
        for sample in 0..12 {
            let then = Instant::now();
            for i in 0..reps {
                model.rebuild(black_box(&map), Range { start: black_box(start + i % 3) });
                black_box(&model.prefix);
                black_box(model.resident_delta);
            }
            if sample > 0 {
                times.push(then.elapsed().as_nanos() as f64 / reps as f64);
            }
        }
        times.sort_by(f64::total_cmp);
        let mut hash: u64 = 0;
        for i in 0..3 {
            model.rebuild(&map, Range { start: start+i });
            for v in model.prefix.iter().chain([&model.resident_delta]) {
                hash = hash.rotate_left(7).wrapping_add(v.to_bits());
            }
        }
        println!("{scenario} {hash:016x} {:.2}", times[times.len()/2]);
    }
}
