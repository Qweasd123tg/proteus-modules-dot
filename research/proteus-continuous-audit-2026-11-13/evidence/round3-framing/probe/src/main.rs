use std::{io::Write, process::{Command,Stdio},time::Duration};
use proteus_process_host::{NewlineJsonFraming,ProcessTransport,ProcessSpec,ProcessTransportLimits};
use serde_json::{Value,json};

// Only the unused receiving-side State is supplied. The writer admission
// function and byte counter come unchanged from Desktop's production source.
#[allow(dead_code)]
mod desktop {
    use std::sync::{Arc,atomic::AtomicBool};
    type Outgoing = serde_json::Value;
    struct State {incoming:Arc<budget::Budget>,closed:AtomicBool}
    #[path="/workspace/scratch/3ba0fff8d310/protocol-desktop/src/declarative/process/budget.rs"]
    mod budget;
    #[path="/workspace/scratch/3ba0fff8d310/protocol-desktop/src/declarative/process/io.rs"]
    mod io;
    pub fn size(value:&Outgoing)->anyhow::Result<usize> {io::encoded_size(value)}
}
#[derive(Default)]
struct Extension;
impl proteus_extension::Extension for Extension {
    fn render(&mut self,_host:&mut proteus_extension::Host,_view:&str,_surface:proteus_extension::Surface,_argument:Option<&str>)->proteus_extension::Result {
        println!("{{\"type\":\"probe_ack\"}}");
        Ok(())
    }
}
fn core_case(limit:usize,json_size:usize) {
    let mut transport=ProcessTransport::spawn_with_limits(
        &ProcessSpec::new("/bin/cat"),NewlineJsonFraming::new(limit),
        ProcessTransportLimits::default().with_write_byte_limits(limit,limit*2,limit*2)).unwrap();
    let message=Value::String("a".repeat(json_size-2));
    assert_eq!(serde_json::to_vec(&message).unwrap().len(),json_size);
    let sent=transport.send_frame(message.clone());
    let got=if sent.is_ok(){Some(transport.recv_frame(Duration::from_secs(5)))}else{None};
    println!("core limit={limit} json_bytes={json_size} send={sent:?} recv={:?}",got.as_ref().map(|x|x.as_ref().map(|v|v==&message)));
    if json_size<limit {assert!(sent.is_ok());assert_eq!(got.unwrap().unwrap(),message);}
    else if json_size==limit {assert!(sent.is_ok());assert!(got.unwrap().is_err());}
    else {assert!(sent.is_err());}
    let _=transport.terminate();
}
fn desktop_case(json_size:usize){
    let limit=16*1024*1024;
    let mut message=json!({"type":"render","context":"c","view":"v","surface":"content","content":{"language":"plain","source":"","context":{}},"session_dir":null});
    let empty=serde_json::to_vec(&message).unwrap().len();
    message["content"]["source"]=json!("a".repeat(json_size-empty));
    let size=desktop::size(&message);
    println!("desktop json_bytes={json_size} admitted_wire_size={size:?}");
    if json_size>limit {assert!(size.is_err());return;}
    assert_eq!(size.unwrap(),json_size+1);
    let mut child=Command::new(std::env::current_exe().unwrap()).arg("--sdk-child")
       .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    {
       let mut stdin=child.stdin.take().unwrap();
       writeln!(stdin,"{}",json!({"type":"hello","protocol":4,"features":[],"workspace":"/tmp","server":{"origin":"","token":""}})).unwrap();
       writeln!(stdin,"{}",json!({"type":"context","context":"c","workspace":"/tmp","session_dir":null})).unwrap();
       serde_json::to_writer(&mut stdin,&message).unwrap();
       stdin.write_all(b"\n").unwrap();
    }
    let output=child.wait_with_output().unwrap();
    let stdout=String::from_utf8(output.stdout).unwrap();
    let stderr=String::from_utf8(output.stderr).unwrap();
    println!("sdk json_bytes={json_size} status={} stdout={stdout:?} stderr={stderr:?}",output.status);
    if json_size<limit{assert!(stdout.contains("probe_ack"));}
    else {assert!(!stdout.contains("probe_ack"));assert!(stderr.contains("exceeds 16 MiB"));}
}
fn main(){
    if std::env::args().any(|a|a=="--sdk-child") {proteus_extension::run(Extension);return;}
    for limit in [32,8*1024*1024] {for size in [limit-1,limit,limit+1] {core_case(limit,size);}}
    let limit=16*1024*1024;
    for size in [limit-1,limit,limit+1] {desktop_case(size);}
}
