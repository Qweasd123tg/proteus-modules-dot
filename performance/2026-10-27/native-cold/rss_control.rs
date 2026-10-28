//! Launcher calibration only; not a Proteus performance workload.
use std::{hint::black_box, io::Write, time::Duration};
fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args[1] == "hold-pipe" {
        unsafe extern "C" {
            fn fork() -> i32;
            fn getpid() -> i32;
        }
        let child = unsafe { fork() };
        assert!(child >= 0);
        if child == 0 {
            std::fs::write(&args[2], unsafe { getpid() }.to_string()).unwrap();
            loop {
                std::thread::sleep(Duration::from_secs(1));
            }
        }
        return;
    }
    let mib: usize = args[1].parse().unwrap();
    assert!([0, 32, 128].contains(&mib));
    let mut bytes = vec![0_u8; mib * 1024 * 1024];
    for index in (0..bytes.len()).step_by(4096) {
        unsafe {
            std::ptr::write_volatile(bytes.as_mut_ptr().add(index), 1);
        }
    }
    black_box(&mut bytes);
    println!("{{\"allocated_mib\":{mib}}}");
    std::io::stdout().flush().unwrap();
    std::thread::sleep(Duration::from_millis(100));
    black_box(bytes);
}
