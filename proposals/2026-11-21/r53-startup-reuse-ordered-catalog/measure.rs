use proteus_contracts::contracts::{SessionLocator, StorageSessionDescriptor};
use std::hint::black_box;
use std::path::Path;
use std::time::Instant;
#[path = "alloc.rs"]
mod alloc;
include!("observed.rs");

fn sample(n: usize, shape: &str) -> Vec<StorageSessionDescriptor> {
    let id = proteus_contracts::domain::new_session_id();
    (0..n)
        .map(|i| {
            let j = match shape {
                "sorted" => n - i,
                "late" => {
                    if i + 1 == n {
                        n + 1
                    } else {
                        n - i
                    }
                }
                "front" => {
                    if i == 0 {
                        0
                    } else {
                        n - i
                    }
                }
                "reverse" => i,
                "scatter" => (i * 9973) % n,
                "tie" => (i % 5) / 2,
                _ => unreachable!(),
            };
            StorageSessionDescriptor {
                session: SessionLocator {
                    session_id: id,
                    key: format!("key-{i:06}"),
                },
                parent_session_id: None,
                workspace_path: "/fixture/project".into(),
                local_path: if shape == "tie" && j == 0 {
                    None
                } else {
                    Some(format!("/fixture/project/catalog/{j:08}").into())
                },
                record_location: None,
                created_at_ms: 0,
                updated_at_ms: if shape == "tie" { 20 } else { j as i64 },
            }
        })
        .collect()
}

fn verify_pair(mut left: Vec<StorageSessionDescriptor>, mut right: Vec<StorageSessionDescriptor>) {
    old_order(&mut left);
    order_startup_candidates(&mut right);
    assert_eq!(left, right);
}

fn measure_case(name: &str, seed: &[StorageSessionDescriptor], reps: usize) {
    let mut times = [Vec::with_capacity(reps), Vec::with_capacity(reps)];
    let mut counts = [None, None];
    let vec_order = [old_order, order_startup_candidates];
    for rep in 0..reps {
        let mut copies = [seed.to_vec(), seed.to_vec()];
        let order = if rep % 2 == 0 { [0, 1] } else { [1, 0] };
        for arm in order {
            let t = Instant::now();
            let (_, out) = alloc::measure(|| vec_order[arm](black_box(&mut copies[arm])));
            times[arm].push(t.elapsed().as_nanos());
            let now = (out.calls, out.bytes);
            if let Some(before) = counts[arm] {
                assert_eq!(before, now);
            } else {
                counts[arm] = Some(now);
            }
        }
        assert_eq!(copies[0], copies[1]);
    }
    let (old, old_bytes) = counts[0].unwrap();
    let (new, new_bytes) = counts[1].unwrap();
    for t in &mut times {
        t.sort_unstable();
    }
    println!(
        "{name} rows={} calls {old}→{new} bytes {old_bytes}→{new_bytes} isolated median ns {}→{}",
        seed.len(),
        times[0][reps / 2],
        times[1][reps / 2]
    );
}

fn main() {
    let path = std::env::args_os().nth(1).unwrap();
    let folder = Path::new(&path);
    println!(
        "bytes per descriptor {}",
        std::mem::size_of::<StorageSessionDescriptor>()
    );
    for n in [0, 1, 10, 31, 32, 64, 128, 512, 4096] {
        for name in ["sorted", "late", "front", "reverse", "scatter", "tie"] {
            measure_case(name, &sample(n, name), 64);
        }
    }
    let mut state: u64 = 1;
    for i in 0..420 {
        let mut seed = sample(i % 145, "tie");
        for j in (1..seed.len()).rev() {
            state = state
                .wrapping_mul(2862933555777941757)
                .wrapping_add(3037000493);
            seed.swap(j, (state % ((j + 1) as u64)) as usize);
        }
        verify_pair(seed.clone(), seed);
    }
    println!("420 shuffled tie/missing-path orders exact");
    for backend in ["jsonl", "sqlite"] {
        for tie in ["distinct", "tied"] {
            let name = format!("real-{backend}-{tie}");
            let rows: Vec<StorageSessionDescriptor> = serde_json::from_slice(
                &std::fs::read(folder.join(format!("{name}.json"))).unwrap(),
            )
            .unwrap();
            measure_case(&name, &rows, 64);
        }
    }
}
