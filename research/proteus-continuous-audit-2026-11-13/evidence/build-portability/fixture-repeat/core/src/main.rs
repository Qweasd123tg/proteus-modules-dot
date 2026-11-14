use std::{io::{self, BufRead, Write},time::Duration};
use proteus_process_host::{ProcessHost,ProcessSpec,NewlineJsonFraming};
use serde_json::json;
const RELEASE: &str = "C";
fn main() {
 if std::env::args().any(|arg| arg == "--version") {println!("{RELEASE}");return;}
 let host = ProcessHost::new(ProcessSpec::new("proteus-model-pack-module"), NewlineJsonFraming::default());
 println!("{}",json!({"event":"started","host":RELEASE,"pid":std::process::id(),"path":std::env::var("PATH").unwrap()}));io::stdout().flush().unwrap();
 for line in io::stdin().lock().lines() {
  let line = line.unwrap(); if line == "quit" { break; }
  if line == "reset" {host.reset();}
  match host.request("release",json!({}),Duration::from_secs(3)) {
   Ok(value)=>println!("{}",json!({"host":RELEASE,"worker":value,"command":line})),
   Err(error)=>println!("{}",json!({"host":RELEASE,"error":format!("{error:#}"),"command":line})),
  };io::stdout().flush().unwrap();
 }
}
