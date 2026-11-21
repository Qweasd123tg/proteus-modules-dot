use super::*;
use std::{env, time::Instant};

#[test]
fn edit_fixture() {
    let dir = env::var("R45_WORKSPACE").unwrap();
    let args: Value = serde_json::from_str(&env::var("R45_ARGS").unwrap()).unwrap();
    let now = Instant::now();
    let result = invoke(&EditFileTool, std::path::Path::new(&dir), args);
    let ns = now.elapsed().as_nanos();
    let status = std::fs::read_to_string("/proc/self/status").unwrap();
    let hwm = status.lines().find_map(|line| line.strip_prefix("VmHWM:")).unwrap()
        .split_whitespace().next().unwrap();
    println!("R45 {ns} {hwm} {}", serde_json::to_string(&result).unwrap());
}
