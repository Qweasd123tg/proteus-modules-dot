use proteus_example_usage_attribution::{MAX_INPUT_BYTES, decode_payload, encode_report};
use std::io::{Read, Write};

fn main() {
    if let Err(message) = run() {
        eprintln!("{message}");
        std::process::exit(2);
    }
}

fn run() -> Result<(), String> {
    if std::env::args_os().len() != 1 {
        return Err("this example accepts stdin only; no arguments".into());
    }
    let mut input = Vec::new();
    std::io::stdin()
        .lock()
        .take((MAX_INPUT_BYTES + 1) as u64)
        .read_to_end(&mut input)
        .map_err(|_| "failed to read stdin".to_string())?;
    let report = decode_payload(&input).map_err(|e| e.to_string())?;
    let output = encode_report(&report).map_err(|e| e.to_string())?;
    std::io::stdout()
        .lock()
        .write_all(&output)
        .map_err(|_| "failed to write stdout".to_string())
}
