//! Authored stdio fixture, not an installable third-party MCP server.
use proteus_mcp_sdk_probes::fixture::{Responder, Scenario, Step};
use std::io::{self, BufRead, Read, Write};

fn main() {
    if let Err(error) = run() {
        eprintln!("authored-fixture-error: {error}");
        std::process::exit(2);
    }
}
fn run() -> Result<(), Box<dyn std::error::Error>> {
    let name = std::env::args().nth(1).ok_or("missing authored scenario")?;
    let scenario = Scenario::parse(&name).ok_or("unknown authored scenario")?;
    let mut responder = Responder::new(scenario);
    let stdin = io::stdin();
    let mut input = stdin.lock();
    let stdout = io::stdout();
    let mut output = stdout.lock();
    let stderr = io::stderr();
    let mut trace = stderr.lock();
    for _ in 0..32 {
        let mut bytes = Vec::new();
        let size = (&mut input).take(65_537).read_until(b'\n', &mut bytes)?;
        if size == 0 {
            return Ok(());
        }
        if size > 65_536 || !bytes.ends_with(b"\n") {
            return Err("authored fixture frame limit exceeded".into());
        }
        let request: serde_json::Value = serde_json::from_slice(&bytes)?;
        trace.write_all(b"TRACE ")?;
        serde_json::to_writer(&mut trace, &request)?;
        trace.write_all(b"\n")?;
        trace.flush()?;
        match responder.handle(&request) {
            Step::Reply(response) => {
                serde_json::to_writer(&mut output, &response)?;
                output.write_all(b"\n")?;
                output.flush()?;
            }
            Step::Ignore => {}
            Step::Exit => return Ok(()),
        }
    }
    Err("authored fixture request count limit exceeded".into())
}
