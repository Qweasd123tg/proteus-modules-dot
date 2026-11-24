#!/usr/bin/env python3
"""Compile the pinned staged scan and typed HistoryMutated fixture with genuine Serde."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

SRC="crates/proteus-core/src/core/session_store/remote/snapshot/display_records.rs"
RUSTC="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
CARGO="841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66"
MANIFEST='''[package]
name = "r258-display-scan-proof"
version = "0.0.0"
edition = "2024"
publish = false

[dependencies]
serde = { version = "=1.0.228", features = ["derive"] }
serde_json = "=1.0.151"
uuid = { version = "=1.23.1", default-features = false, features = ["serde"] }
'''


def check(ok, text):
    if not ok:
        raise ValueError(text)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(raw,p,k):
    git=hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
    check((git,sha(raw))==(p["git_blob"],p["sha256"]),"exact identity: "+k)


def part(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]


def prefix_derive(s,decl):
    i=s.index(decl)
    return s[s.rindex("#[derive(",0,i):i]


def item(s,decl):
    body=part(s,decl,"\n}")
    return prefix_derive(s,decl)+body+"\n}\n"


def source_types(r):
    j,m,ids,tool=[r[k] for k in ("journal","messages","ids","tool")]
    alias="".join(line+"\n" for line in ids.splitlines() if line.startswith("pub type ") and "= Uuid;" in line)
    alias+='pub type CallId = String;\n'
    e="pub struct ExecutionId(Uuid);"
    ex=prefix_derive(ids,e)+e+"\n"
    selected_entry=(prefix_derive(j,"pub enum JournalEntry {")
                    +'pub enum JournalEntry {\n    HistoryMutated(HistoryMutated),\n}\n')
    check("    HistoryMutated(HistoryMutated)," in j,"exact entry variant")
    text=part(m,"    Text {","    Context {")
    selected_part=(prefix_derive(m,"pub enum ContentPart {")
                   +"pub enum ContentPart {\n"+text+"}\n")
    binding=item(r["wcheckpoint"],"pub struct WorkflowToolResultBinding {")
    binding=binding.replace("crate::contracts::","")
    records=(item(j,"pub enum HistoryMutationKind {")+item(j,"pub struct HistoryMutated {")
             +selected_entry+item(j,"pub struct JournalRecord {")).replace("crate::contracts::","")
    return (alias+ex+item(m,"pub enum MessageRole {")+item(m,"pub enum MessagePhase {")
            +item(m,"pub struct CanonicalMessage {")+item(m,"pub enum PartProvenance {")
            +item(m,"pub enum PartScope {")+item(m,"pub struct CanonicalPart {")+selected_part
            +item(tool,"pub struct ToolCall {")+item(tool,"pub enum ToolCallSurface {")
            +part(r["report"],"#[derive(Debug, Clone, Serialize").replace("crate::domain::","")+binding+records)


def locked_deps(repo,dep,base_archives,meta):
    proof=(dep/"lockseed-min"/"Cargo.lock").read_bytes()
    check(sha(proof)==meta["proof_lock_sha256"],"isolated Cargo.lock")
    lock={(i["name"],i["version"]):i.get("checksum") for i in tomllib.loads(repo)["package"]}
    instances=[i for i in tomllib.loads(proof.decode())["package"] if "source" in i]
    for i in instances:
        key=(i["name"],i["version"]);name="-".join(key)
        chk=i["checksum"]
        archive=(dep/"archives" if key[0]=="uuid" else base_archives)/(name+".crate")
        check(lock[key]==chk and sha(archive.read_bytes())==chk,"official archive "+name)
        root=dep/"vendor"/name
        checked=json.loads((root/".cargo-checksum.json").read_text())
        check(checked["package"]==chk,"vendor checksum "+name)
        for rel,digest in checked["files"].items():
            path=root/rel
            check(path.resolve(strict=True).is_relative_to(root.resolve(strict=True))
                  and not path.is_symlink() and sha(path.read_bytes())==digest,"vendor file "+name+"/"+rel)
    v={x["name"]:x["version"] for x in instances}
    check(v["serde"]=="1.0.228" and v["serde_json"]=="1.0.151" and v["uuid"]=="1.23.1","real parser and UUID")
    return proof


def apply(root,env,git,patch,meta,stock):
    pin(patch,meta["patch"],"source patch")
    p=root/SRC;p.parent.mkdir(parents=True)
    p.write_bytes(stock); q=root/"source.patch";q.write_bytes(patch)
    git_env=env | {"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
                   "GIT_CEILING_DIRECTORIES":str(root.parent)}
    def step(flags):
        for mode in (["--check"],[]):
            subprocess.run([git,"apply",*flags,*mode,q],cwd=root,env=git_env,check=True,timeout=20)
    step([])
    changed=p.read_bytes();pin(changed,meta["candidate"],"postimage")
    step(["-R"]);check(p.read_bytes()==stock,"exact rollback")
    return changed


def variant(tag,s):
    fn=part(s,"    pub(crate) fn scan(")
    fn=fn.replace("anyhow::ensure!","ensure!")
    # An identical second lift observes the owned raw allocation immediately after LF validation.
    trace=fn.replace("fn scan(","fn traced_scan(",1)
    anchor="            consume(serde_json::from_slice(&line)?)?;" if tag=="stock" else "            let record = serde_json::from_slice(&line)?;"
    check(trace.count(anchor)==1,"one trace anchor before real decode")
    trace=trace.replace(anchor,"            watch(&line);\n"+anchor)
    threshold=re.search(r"(?m)^const MAX_RETAINED_FINAL_SCAN_BYTES.*$",s)
    threshold=(threshold[0]+"\n") if threshold else ""
    # Both slices include the DisplayRecords impl closing brace, remove the first.
    fn=fn[:fn.rindex("}")]
    return (f"mod {tag} {{\nuse super::*;\n"+threshold+
            "pub(super) struct DisplayRecords {file:Input,count:usize}\nimpl DisplayRecords {\n"+
            fn+trace+RUNNER+"}\n")


SUPPORT=r'''
#![allow(dead_code)]
use serde::{Deserialize,Serialize};
use uuid::Uuid;
use std::{alloc::{GlobalAlloc,Layout,System},cell::Cell,fs::{File,OpenOptions},
          io::{self,BufRead,BufReader,Cursor,Read,Seek,SeekFrom,Write},
          sync::atomic::{AtomicUsize,Ordering}};
type Result<T>=std::result::Result<T,Box<dyn std::error::Error>>;
macro_rules! ensure {
    ($ok:expr,$cause:literal)=>{if !$ok {return Err($cause.into());}};
}

enum Source { File(File), Fault(Cursor<Vec<u8>>) }
struct Input {source:Source, reads:usize, rewind_failure:bool}
impl Read for Input {
    fn read(&mut self,dst:&mut [u8])->io::Result<usize>{
        self.reads+=1;
        match &mut self.source {
            Source::File(file)=>file.read(dst),
            Source::Fault(cursor) if cursor.position() as usize==cursor.get_ref().len() =>
                Err(io::Error::other("fixture late I/O")),
            Source::Fault(cursor)=>cursor.read(dst),
        }
    }
}
impl Seek for Input {
    fn seek(&mut self, pos:SeekFrom)->io::Result<u64>{
        if self.rewind_failure{return Err(io::Error::other("fixture rewind failure"));}
        match &mut self.source {Source::File(file)=>file.seek(pos),Source::Fault(cursor)=>cursor.seek(pos)}
    }
}
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Observation {ptr:usize,capacity:usize,released:bool}
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Stats {alloc:usize,realloc:usize,bytes:usize}
thread_local! {
    static RAW:Cell<Observation>=const {Cell::new(Observation{ptr:0,capacity:0,released:false})};
    static METER:Cell<Option<Stats>>=const {Cell::new(None)};
}
fn watch(line:&Vec<u8>) { RAW.set(Observation{ptr:line.as_ptr() as usize,capacity:line.capacity(),released:false}); }
fn request(n:usize,re:bool) {
    let _=METER.try_with(|m|if let Some(mut s)=m.get(){
        if re{s.realloc+=1;}else{s.alloc+=1;}s.bytes+=n;m.set(Some(s));
    });
}
struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {request(n,true);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){
        let _=RAW.try_with(|r|{
            let mut o=r.get();
            if o.ptr==p as usize && o.capacity==l.size()&&!o.released {
                o.released=true;r.set(o);
            }
        });
        unsafe{System.dealloc(p,l)}
    }
}
#[global_allocator] static ALLOCATOR:Meter=Meter;
#[derive(Debug,PartialEq,Eq)]
enum Status { Ok, Frame, Parse, Count, Callback, Late, Rewind }
fn status(r:Result<()>)->Status {
    match r {
        Ok(())=>Status::Ok,
        Err(e) if e.downcast_ref::<serde_json::Error>().is_some()=>Status::Parse,
        Err(e)=>match e.to_string().as_str(){
            "incomplete transcript staging record"=>Status::Frame,
            "transcript staging record count changed"=>Status::Count,
            "fixture callback error"=>Status::Callback,
            "fixture late I/O"=>Status::Late,
            "fixture rewind failure"=>Status::Rewind,
            other=>panic!("unexpected error: {other}"),
        }
    }
}
#[derive(Debug,PartialEq,Eq)]
struct Receipt {status:Status,reads:usize,calls:Vec<(u64,i64)>,caps:Vec<(usize,bool)>}
'''

RUNNER=r'''
impl DisplayRecords {
    pub(super) fn new(file:Input,count:usize)->Self {Self{file,count}}
    pub(super) fn run(&mut self,expected:&[&JournalRecord],stop:Option<usize>,trace:bool)->Receipt {
        let mut calls=Vec::new();let mut caps=Vec::new();
        RAW.set(Observation::default());
        let start=self.file.reads;
        let mut consume=|record:JournalRecord|->Result<()>{
            let i=calls.len();
            assert_eq!(&record,expected[i]);
            calls.push((record.session_seq,record.timestamp_ms));
            if trace {let o=RAW.get();caps.push((o.capacity,o.released));}
            if Some(i)==stop {return Err("fixture callback error".into());}
            Ok(())
        };
        let s=if trace {self.traced_scan(&mut consume)} else {self.scan(&mut consume)};
        Receipt{status:status(s),reads:self.file.reads-start,calls,caps}
    }
    pub(super) fn allocations(&mut self,expected:&[&JournalRecord])->(Stats,usize) {
        RAW.set(Observation::default());
        assert!(METER.replace(Some(Stats::default())).is_none());
        let mut n=0;
        let s=self.scan(|record|{assert_eq!(&record,expected[n]);n+=1;Ok(())});
        let stats=METER.take().unwrap();
        assert!(s.is_ok());
        (stats,n)
    }
}
'''

TESTS=r'''
const THRESHOLD:usize=4*1024*1024;
fn uid(i:usize)->Uuid { Uuid::from_u128(i as u128+1) }
fn text(i:usize,s:String)->CanonicalMessage{
    let role=if i%2==0 {MessageRole::User}else{MessageRole::Assistant};
    let provenance=if i%2==0 {PartProvenance::User}else{PartProvenance::Model};
    CanonicalMessage{id:uid(i*2+101),role,phase:None,
        parts:vec![CanonicalPart{part_id:uid(i*2+102),provenance,scope:PartScope::Conversation,
                                payload:ContentPart::Text{text:s}}],
        name:None,tool_call_id:None,metadata:serde_json::Value::Null}
}
fn record(seq:u64,messages:Vec<CanonicalMessage>)->JournalRecord {
    JournalRecord{schema_version:21,record_id:uid(seq as usize),session_seq:seq,timestamp_ms:19-seq as i64,
        session_id:uid(800),execution_id:None,thread_id:Some(uid(900)),turn_id:None,
        entry:JournalEntry::HistoryMutated(HistoryMutated{previous_revision:seq-1,new_revision:seq,
              mutation:HistoryMutationKind::Append,messages,compaction:None,tool_results:vec![]})}
}
fn many(seq:u64,n:usize)->JournalRecord {
    let body="Синтетический текст для замера памяти и прокрутки. ".repeat(4);
    record(seq,(0..n).map(|i|text(i,format!("Fixture row {i}\n{body}"))).collect())
}
fn sized(seq:u64,bytes:usize)->JournalRecord {record(seq,vec![text(0,"a".repeat(bytes))])}
fn physical(rows:&[&JournalRecord],after:&[u8])->(Input,u64) {
    static NEXT:AtomicUsize=AtomicUsize::new(0);
    let p=std::env::temp_dir().join(format!("scan-fixture-{}-{}",std::process::id(),NEXT.fetch_add(1,Ordering::Relaxed)));
    let mut file=OpenOptions::new().create_new(true).read(true).write(true).open(&p).unwrap();
    std::fs::remove_file(&p).unwrap();
    {
        let mut writer=std::io::BufWriter::new(&mut file);
        for r in rows {serde_json::to_writer(&mut writer,r).unwrap();writer.write_all(b"\n").unwrap();}
        writer.write_all(after).unwrap();
        writer.flush().unwrap();
    }
    let len=file.stream_position().unwrap();
    (Input{source:Source::File(file),reads:0,rewind_failure:false},len)
}
fn pair(rows:&[&JournalRecord],tail:&[u8],count:usize,stop:Option<usize>,trace:bool)->(Receipt,Receipt,u64){
    let (a,bytes)=physical(rows,tail);let (b,other)=physical(rows,tail);assert_eq!(bytes,other);
    let a=stock::DisplayRecords::new(a,count).run(rows,stop,trace);
    let b=candidate::DisplayRecords::new(b,count).run(rows,stop,trace);
    assert_eq!((&a.status,a.reads,&a.calls),(&b.status,b.reads,&b.calls));
    (a,b,bytes)
}

#[test]
fn fifty_thousand_text_rows_real_serde_lf_and_rewind_drop_raw_before_callback() {
    let row=many(1,50_000);let (a,bytes)=physical(&[&row],b"");let (b,_)=physical(&[&row],b"");
    let mut a=stock::DisplayRecords::new(a,1);let mut b=candidate::DisplayRecords::new(b,1);
    for _ in 0..2 {
        let old=a.run(&[&row],None,true);let new=b.run(&[&row],None,true);
        assert_eq!((&old.status,old.reads,&old.calls),(&new.status,new.reads,&new.calls));
        assert_eq!(old.status,Status::Ok);assert_eq!(old.calls.len(),1);
        assert_eq!(old.caps.len(),1);assert_eq!(new.caps.len(),1);
        assert_eq!(old.caps[0].0,new.caps[0].0);assert!(old.caps[0].0>THRESHOLD);
        assert!(!old.caps[0].1);assert!(new.caps[0].1);
        println!("R258_RAW {bytes} {}",old.caps[0].0);
    }
}
#[test]
fn small_exact_threshold_two_large_and_earlier_large_final_small() {
    let small=sized(2,13);
    let med=sized(1,3*1024*1024);
    let big=sized(1,5*1024*1024);
    let big2=sized(2,5*1024*1024);
    let (a,b,_)=pair(&[&small],b"",1,None,true);
    assert_eq!(a.caps,b.caps);assert!(!b.caps[0].1);
    let (a,b,_)=pair(&[&med],b"",1,None,true);
    assert_eq!(a.caps,b.caps);assert_eq!(b.caps[0],(THRESHOLD,false));
    for last in [&small,&big2] {
        let (a,b,_)=pair(&[&big,last],b"",2,None,true);
        assert!(!a.caps[0].1&&!a.caps[1].1);assert!(!b.caps[0].1&&b.caps[1].1);
        assert_eq!(a.caps[0].0,b.caps[0].0);assert_eq!(a.caps[1].0,b.caps[1].0);
        assert!(b.caps[1].0>THRESHOLD);
    }
}
#[test]
fn expected_count_is_never_a_stop_or_an_admission_rule() {
    let big=sized(1,5*1024*1024);
    let next=sized(2,3);
    let (_,b,_)=pair(&[&big,&next],b"",1,None,true);
    assert_eq!(b.status,Status::Count);
    assert_eq!(b.calls.len(),2);
    assert!(b.caps[0].1);
    let (_,b,_)=pair(&[&big],b"",2,None,true);
    assert_eq!(b.status,Status::Count);
    assert_eq!(b.calls.len(),1);
    assert!(!b.caps[0].1);
    let (_,b,_)=pair(&[&next],b"",0,None,true);
    assert_eq!(b.status,Status::Count);
    assert_eq!(b.calls.len(),1);
}
#[test]
fn missing_lf_malformed_extra_and_callback_preserve_error_precedence() {
    let big=sized(1,5*1024*1024);
    let valid=serde_json::to_vec(&sized(2,4)).unwrap();
    let (_,b,_)=pair(&[&big],&valid,1,None,false);
    assert_eq!((b.status,b.calls.len()),(Status::Frame,1));
    let (_,b,_)=pair(&[&big],b"{broken}\n",1,None,false);
    assert_eq!((b.status,b.calls.len()),(Status::Parse,1));
    let (_,b,_)=pair(&[&big],b"{broken}",1,None,false);
    assert_eq!((b.status,b.calls.len()),(Status::Frame,1));
    let (_,b,_)=pair(&[&big],b"{broken}\n",1,Some(0),false);
    assert_eq!((b.status,b.calls.len()),(Status::Callback,1));
    let (_,b,_)=pair(&[],b"{broken}\n",0,None,false);
    assert_eq!((b.status,b.calls.len()),(Status::Parse,0));
}
#[test]
fn late_read_and_rewind_faults_remain_observable() {
    let row=sized(1,16);
    let mut logical=serde_json::to_vec(&row).unwrap();logical.push(b'\n');
    for (stop,rewind,want,reads,calls) in [
        (None,false,Status::Late,2,1),
        (Some(0),false,Status::Callback,1,1),
        (None,true,Status::Rewind,0,0),
    ] {
        let input=||Input{source:Source::Fault(Cursor::new(logical.clone())),reads:0,rewind_failure:rewind};
        let a=stock::DisplayRecords::new(input(),1).run(&[&row],stop,false);
        let b=candidate::DisplayRecords::new(input(),1).run(&[&row],stop,false);
        assert_eq!(a,b);
        assert_eq!((b.status,b.reads,b.calls.len()),(want,reads,calls));
    }
    let huge=sized(1,5*1024*1024);
    let mut bytes=serde_json::to_vec(&huge).unwrap();
    bytes.push(b'\n');
    let mut before_late=None;
    for (stop,want) in [(Some(0),Status::Callback),(None,Status::Late)] {
        let input=||Input{source:Source::Fault(Cursor::new(bytes.clone())),reads:0,rewind_failure:false};
        let a=stock::DisplayRecords::new(input(),1).run(&[&huge],stop,true);
        let b=candidate::DisplayRecords::new(input(),1).run(&[&huge],stop,true);
        assert_eq!((&a.status,a.reads,&a.calls),(&b.status,b.reads,&b.calls));
        assert_eq!(b.status,want);
        assert_eq!(b.calls.len(),1);
        assert!(a.caps[0].0>THRESHOLD && !a.caps[0].1);
        assert_eq!(b.caps[0],(a.caps[0].0,true));
        if let Some(base)=before_late {assert_eq!(b.reads,base+1);}
        else {before_late=Some(b.reads);}
    }
}
#[test]
fn common_and_repeated_large_valid_scans_do_not_repeat_allocator_requests() {
    let small=sized(1,40);
    let large=sized(1,5*1024*1024);
    let second=sized(2,5*1024*1024);
    for (tag,rows) in [("small",vec![&small]),("large-pair",vec![&large,&second])] {
        let (a,_)=physical(&rows,b"");let (b,_)=physical(&rows,b"");
        let (x,xc)=stock::DisplayRecords::new(a,rows.len()).allocations(&rows);
        let (y,yc)=candidate::DisplayRecords::new(b,rows.len()).allocations(&rows);
        assert_eq!((x,xc),(y,yc));
        println!("R258_REQ {tag} {} {} {}",x.alloc,x.realloc,x.bytes);
    }
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("refs","work","rustc","cargo","deps"):
        p.add_argument("--"+k,type=Path,required=True)
    p.add_argument("--base-archives",type=Path,required=True)
    p.add_argument("--git",type=Path,default=Path("/usr/bin/git"))
    a=p.parse_args()
    pkg=Path(__file__).parent
    meta=json.loads((pkg/"SOURCE-PROVENANCE.json").read_text())
    refs={}
    for k,pin_ in meta["inputs"].items():
        b=(a.refs/(k+".ref")).read_bytes()
        pin(b,pin_,k);refs[k]=b
    dep=a.deps.resolve(strict=True)
    locked=locked_deps(refs["lock"].decode(),dep,a.base_archives.resolve(strict=True),meta)
    rustc=a.rustc.resolve(strict=True);cargo=a.cargo.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC and sha(cargo.read_bytes())==CARGO,"verified tools")
    with tempfile.TemporaryDirectory(prefix="r258-",dir=a.work.resolve(strict=True)) as tmp:
        root=Path(tmp)
        env={"PATH":"/usr/bin:/bin","HOME":tmp,"TMPDIR":tmp,"LC_ALL":"C","RUSTC":str(rustc),
             "CARGO_HOME":str(root/"cargo-home"),"CARGO_TARGET_DIR":str(root/"target")}
        changed=apply(root,env,a.git.resolve(strict=True),(pkg/"source.patch").read_bytes(),meta,refs["staged"])
        r={k:v.decode() for k,v in refs.items()}
        check("Some(records) => records.scan(consume)" in r["snapshot"] and "None => self.scan_from(0, is_display_kind, consume)" in r["snapshot"],
              "actual staged scan call")
        code=SUPPORT+source_types(r)+variant("stock",r["staged"])+variant("candidate",changed.decode())+TESTS
        (root/"Cargo.toml").write_text(MANIFEST)
        (root/"Cargo.lock").write_bytes(locked)
        (root/"src").mkdir();(root/"src"/"lib.rs").write_text(code)
        cmd=[cargo,"test","--offline","--locked","--config",'source.crates-io.replace-with="r258-official-verified"',
             "--config","source.r258-official-verified.directory="+json.dumps(str(dep/"vendor"))]
        results={}
        for mode,flags in [("debug",[]),("optimized",["--release"])]:
            out=subprocess.run([*cmd,*flags,"--lib","--","--test-threads=1","--nocapture"],cwd=root,
                               env=env,capture_output=True,text=True,timeout=180)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 6 passed; 0 failed;" in out.stdout,"test count")
            exact=re.findall(r"(?m)\bR258_RAW (\d+) (\d+)$",out.stdout)
            check(len(exact)==2 and exact[0]==exact[1],"two rewind receipts")
            requests={x:list(map(int,y.split())) for x,y in re.findall(r"(?m)\bR258_REQ (\S+) ((?:\d+ ){2}\d+)$",out.stdout)}
            check(set(requests)=={"small","large-pair"},"scoped allocator parity")
            results[mode]=dict(tests_passed=6,stage_bytes=int(exact[0][0]),raw_capacity_bytes=int(exact[0][1]),
                raw_allocation_released_before_callback=[False,True],requests_identical_both_arms=requests)
            print(f"PASS {mode}",flush=True)
        print(json.dumps(dict(status="PASS",serde_json="1.0.151",uuid="1.23.1",native_worker_core_renderer=False,
                              threshold=4*1024*1024,results=results),indent=2))


if __name__=="__main__":
    main()
