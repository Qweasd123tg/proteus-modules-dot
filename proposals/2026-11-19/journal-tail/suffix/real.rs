use std::{
    fs, io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{Arc, Mutex},
    time::Instant,
};
use anyhow::{Context, Result, ensure};
use async_trait::async_trait;
use proteus_contracts::{contracts::{SessionStorage, SessionStorageRequest as Req, SessionStorageResponse as Res}, domain::SessionId};
use serde_json::{Value, json};

struct Pipe { child: Child, sink: ChildStdin, stream: BufReader<ChildStdout>, seq: u64, compares: usize, last_reply_bytes: usize, record_bytes: usize, offsets: Vec<u64> }
impl Drop for Pipe { fn drop(&mut self) { self.child.kill().ok(); self.child.wait().ok(); } }
impl Pipe {
    fn new() -> Self {
        let mut child=Command::new(std::env::var_os("PERF7_WORKER").unwrap()).stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().unwrap();
        let sink=child.stdin.take().unwrap();let stream=BufReader::new(child.stdout.take().unwrap());
        let mut pipe=Self{child,sink,stream,seq:0,compares:0, last_reply_bytes:0, record_bytes:0, offsets:Vec::new()};
        pipe.call("initialize", json!({"protocol_version":"v3","component_id":"display-replay","exports":[{"slot":"session_storage","module_id":"jsonl","contract_version":"v1","composition":"select_one","module_config":{},"host_features":[]}]})).unwrap();
        pipe
    }
    fn call(&mut self, name:&str, args:Value)->Result<Value> {
        let id=format!("h:1:{}",self.seq); self.seq+=1;
        serde_json::to_writer(&mut self.sink,&json!({"jsonrpc":"2.0","id":id,"method":name,"params":args}))?;
        self.sink.write_all(b"\n")?; self.sink.flush()?;
        let mut line=String::new();self.stream.read_line(&mut line)?;self.last_reply_bytes=line.len();
        let response:Value=serde_json::from_str(&line)?;
        ensure!(response["id"]==id && response.get("error").is_none(),"worker: {}",response);
        response.get("result").cloned().context("no result")
    }
}
struct Worker(Mutex<Pipe>);
#[async_trait]
impl SessionStorage for Worker {
    async fn execute(&self, req:Req)->Result<Res> { self.execute_blocking(req) }
    fn execute_blocking(&self, req:Req)->Result<Res>{
        let mut pipe=self.0.lock().unwrap();
        let records=matches!(req, Req::ReadRecords{..});
        match &req { Req::CompareSnapshots{..}=>pipe.compares+=1,Req::ReadRecords{after_seq,..}=>pipe.offsets.push(*after_seq),_=>{} }
        let id=format!("h:1:{}",pipe.seq);
        let params=json!({"export":{"slot":"session_storage","module_id":"jsonl"},"lineage":{"root_invocation_id":id,"parent_invocation_id":null,"depth":0},"params":req});
        let response=pipe.call("execute",params)?;if records{pipe.record_bytes+=pipe.last_reply_bytes;}
        Ok(serde_json::from_value(response)?)
    }
}
fn cpu(pid: i32) -> f64 {
    let mut clock = 0;
    let mut time = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe {
        assert_eq!(libc::clock_getcpuclockid(pid, &mut clock), 0);
        assert_eq!(libc::clock_gettime(clock, &mut time), 0);
    }
    time.tv_sec as f64 * 1000. + time.tv_nsec as f64 / 1e6
}
#[test]
fn replay_captured_dogfood_turn() {
    use crate::core::session_store::remote::{RemoteSessionStore,prepared::PreparedSession};
    use crate::app_server::{journal_transcript_from_source, journal_transcript_append_from_source};
    let tmp=tempfile::tempdir().unwrap();
    let session=fs::read_to_string(std::env::var_os("PERF7_CAPTURE").unwrap()).unwrap();
    let rows:Vec<&str>=session.split_inclusive('\n').collect();
    let metadata:Vec<Value>=rows.iter().map(|row|serde_json::from_str(row).unwrap()).collect();
    let id:SessionId=serde_json::from_value(metadata[0]["session_id"].clone()).unwrap();
    let split=metadata.iter().position(|r|r["kind"]=="turn_opened").unwrap();
    let worker=Arc::new(Worker(Mutex::new(Pipe::new())));
    let root=tmp.path().join("home");let cwd=tmp.path().join("work");fs::create_dir_all(&cwd).unwrap();
    let store=RemoteSessionStore::new(worker.clone(),&root,&cwd,id).unwrap();
    let Res::Writer{lease,..}=store.request(Req::AcquireWriter{session:store.descriptor.session.clone()}).unwrap() else { panic!("not writer") };
    store.request(Req::ReleaseWriter{lease}).unwrap();
    let journal=store.session_dir().join("journal.jsonl");
    fs::write(&journal,rows[..split].concat()).unwrap();
    let cold=PreparedSession::from_dir(worker.clone(),store.session_dir().into()).unwrap();
    let (store,old,deferred,stale)=cold.into_display_view(|src|journal_transcript_from_source(src,None)).unwrap();
    assert!(!deferred && !stale);let first=old.cursor.unwrap().revision;
    fs::OpenOptions::new().append(true).open(&journal).unwrap().write_all(rows[split..].concat().as_bytes()).unwrap();
    {let mut counters=worker.0.lock().unwrap();counters.compares=0;counters.offsets.clear();counters.record_bytes=0;}
    let pid=worker.0.lock().unwrap().child.id() as i32;
    let core0=cpu(0);let storage0=cpu(pid);let start=Instant::now();
    let mut fallback=false;
    let full=|src:&mut crate::core::JournalReadSnapshot|{fallback=true;journal_transcript_from_source(src,None)};
    #[cfg(after)]
    let projected=store.project_read_view(full,crate::app_server::PrefixIdentities::observe,journal_transcript_append_from_source).unwrap();
    #[cfg(not(after))]
    let projected=store.project_read_view(full,journal_transcript_append_from_source).unwrap();
    let elapsed=start.elapsed();let core=cpu(0)-core0;let storage=cpu(pid)-storage0;
    let base=projected.cursor.as_ref().unwrap().base.as_ref().unwrap();
    assert_eq!(base.revision,first);
    let (compares,offsets,record_bytes)={let c=worker.0.lock().unwrap();(c.compares,c.offsets.clone(),c.record_bytes)};
    eprintln!("capture old={} new={} strict_messages={} projected_total={} prefix_rows={} fallback={fallback} compares={compares} read_offsets={offsets:?} records_reply_bytes={record_bytes} core_cpu_ms={core:.3} storage_cpu_ms={storage:.3} projection_ms={:.3}",
              split,rows.len()-split,projected.summary.message_count,
              projected.cursor.as_ref().unwrap().before + projected.transcript.len(),base.common_prefix, elapsed.as_secs_f64()*1000.);
    let cache=store.fresh_read_model().unwrap();
    let full=store.project_read_model(|src|journal_transcript_from_source(src,None)).unwrap();
    assert_eq!(serde_json::to_value(cache).unwrap(),serde_json::to_value(full).unwrap());
}
