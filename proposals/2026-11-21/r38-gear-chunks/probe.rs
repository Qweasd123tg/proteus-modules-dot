// Linux-only bench; top-level inputs are the unmodified IO code and the actual
// old/new blob_codec.rs (the non-timing build adds a counter at the Gear update).
#![allow(dead_code)]
mod io;
mod stock;
mod candidate;
use std::{hint::black_box, path::Path, time::Instant};

#[cfg(gear_count)]
thread_local! { static LOOKUPS: std::cell::Cell<u64> = const { std::cell::Cell::new(0) }; }

#[repr(C)]
struct Timespec { sec: std::ffi::c_long, nsec: std::ffi::c_long }
unsafe extern "C" { fn clock_gettime(clock: std::ffi::c_int, t: *mut Timespec) -> std::ffi::c_int; }
fn cpu_ns() -> u64 {
    let mut t = Timespec { sec:0, nsec:0 };
    assert_eq!(unsafe { clock_gettime(2, &mut t) }, 0); // Linux CLOCK_PROCESS_CPUTIME_ID
    t.sec as u64 * 1_000_000_000 + t.nsec as u64
}
fn input(mode: &str, n: usize, mut state: u64) -> Vec<u8> {
    match mode {
        "zero" => vec![0; n],
        "random" => (0..n).map(|_| {
            state ^= state << 13; state ^= state >> 7; state ^= state << 17; state as u8
        }).collect(),
        "json" => {
            let unit = br#"{"role":"user","content":"sample text for replay"},"#;
            unit.iter().copied().cycle().take(n).collect()
        }
        _ => unreachable!()
    }
}
fn chunk_count(manifest: &[u8]) -> usize { stock::chunk_files(manifest).unwrap().len() }
fn work(dir: &Path, bytes: &[u8], is_new: bool) -> (Vec<u8>, u64, u128, u64) {
    #[cfg(gear_count)] LOOKUPS.set(0);
    let cpu = cpu_ns(); let real = Instant::now();
    let pack = if is_new { candidate::pack } else { stock::pack };
    let value = black_box(pack(black_box(dir),black_box(bytes)).unwrap());
    let elapsed = real.elapsed().as_nanos(); let cpu = cpu_ns()-cpu;
    #[cfg(gear_count)] let updates = LOOKUPS.get();
    #[cfg(not(gear_count))] let updates = 0;
    (value,cpu,elapsed,updates)
}
fn main() {
    let a = tempfile::tempdir().unwrap(); let b = tempfile::tempdir().unwrap();
    // Independent initial directories; compare persisted manifest and the
    // reconstruction by both versions including cross-reading and raw inputs.
    let sizes: &[usize] = &[0,1,16383,16384,16385,32767,65535,65536,65537,131089,262144,1048576];
    let mut cases=0;
    for n in sizes {
        for (mode,seed) in [("zero",1),("json",1),("random",1),("random",7),("random",127)] {
            let v=input(mode,*n,seed);
            let x=stock::pack(a.path(),&v).unwrap(); let y=candidate::pack(b.path(),&v).unwrap();
            assert_eq!(x,y);
            for dir in [a.path(), b.path()] {
                assert_eq!(stock::unpack(dir,&y).unwrap().as_ref(),v);
                assert_eq!(candidate::unpack(dir,&x).unwrap().as_ref(),v);
            }
            cases+=1;
        }
    }
    println!("PARITY,{cases}");
    let warm = tempfile::tempdir().unwrap();
    for (mode,n) in [("zero",16383),("random",262144),("json",262144),("random",4194304),("zero",4194304)] {
        let v=input(mode,n,107);
        let manifest=stock::pack(warm.path(),&v).unwrap();
        assert_eq!(candidate::pack(warm.path(),&v).unwrap(),manifest);
        let nc=chunk_count(&manifest);
        let expected_hash=io::sha256_hex(&manifest);
        #[cfg(gear_count)] let rounds=1;
        #[cfg(not(gear_count))] let rounds=27;
        for r in 0..rounds {
            for new in [r%2==1,r%2==0] {
                let (m,cpu,elapsed,updates)=work(warm.path(),&v,new);
                assert_eq!(m,manifest);
                println!("ROW,{mode},{n},{nc},{r},{new},{cpu},{elapsed},{updates},{expected_hash}");
            }
        }
    }
}
