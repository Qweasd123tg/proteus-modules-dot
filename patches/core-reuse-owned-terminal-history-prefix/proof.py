#!/usr/bin/env python3
"""Exact terminal history preparation and validation; no storage or provider."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

SRC="crates/proteus-core/src/core/runtime"
RUSTC_SHA="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION="rustc 1.95.0 (59807616e 2026-04-14)"


def check(ok,label):
    if not ok:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pin(raw,expected,label):
    git=hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()
    check((git,sha(raw))==(expected["git_blob"],expected["sha256"]),f"identity: {label}")


def part(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]


def serde_free(s):
    return re.sub(r"(?m)^#\[serde\([^\n]+\)\]\n","",s).replace(", Serialize, Deserialize","")


def contract(r):
    m=r["messages"]
    t=r["tool"]
    body=part(m,"#[derive(Debug, Clone, Serialize","\n#[cfg(test)]")
    alias=re.search(r"(?m)^pub type CallId = String;$",r["ids"])[0]+"\n"
    call=("#[derive(Debug,Clone,PartialEq)]\n"+part(t,"pub struct ToolCall {","    pub fn with_surface(")+"}\n"
          +"#[derive(Debug,Clone,Copy,PartialEq,Eq,Default)]\n"+part(t,"pub enum ToolCallSurface {","impl ToolCallSurface"))
    result=("#[derive(Debug,Clone,PartialEq)]\n"+part(t,"pub struct ToolResult {","#[cfg(test)]"))
    report=part(r["report"],"#[derive(Debug, Clone, Serialize")
    image=("#[derive(Debug,Clone,PartialEq,Eq)]\n"
           +part(r["image"],"pub struct ImageRef {","\n}\n")+"\n}\n")
    return serde_free(alias+call+result+report+image+body)


def verify_git(root,env,git,refs,packet,data):
    context=env | {"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
                   "GIT_CEILING_DIRECTORIES":str(root.parent)}
    d=root/SRC
    d.mkdir(parents=True)
    for k in ["history","turn"]:
        (d/(k+".rs")).write_bytes(refs[k])
    patch=(packet/"source.patch").read_bytes()
    pin(patch,data["patch"],"patch")
    pp=root/"source.patch";pp.write_bytes(patch)
    def apply(reverse=False):
        direction=["-R"] if reverse else []
        for step in (["--check"],[]):
            subprocess.run([git,"apply",*direction,*step,pp],cwd=root,env=context,check=True,timeout=20)
    apply()
    out={k:(d/(k+".rs")).read_bytes() for k in ["history","turn"]}
    for k,b in out.items():
        pin(b,data["candidate"][k],k)
    apply(True)
    for k in out:
        check((d/(k+".rs")).read_bytes()==refs[k],"exact two-file rollback")
    h="\nimpl super::AgentRuntime".encode()
    check(refs["history"].split(h)[1]==out["history"].split(h)[1],
          "actual commit/refresh and embedded tests are exact unchanged bytes")
    p=b"    AgentRuntime, ExecutionAdmissionSnapshot, ReservedRunCompletion,\n    history::prepare_owned_history_update,"
    q=b"        let history_update = match prepare_owned_history_update(\n            history,"
    check(out["turn"].replace(p,b"    AgentRuntime, ExecutionAdmissionSnapshot, ReservedRunCompletion, prepare_history_update,")
          .replace(q,b"        let history_update = match prepare_history_update(\n            &history,")==refs["turn"],
          "exact turn only changes import and call")
    return out


def variant(tag,h,t,refs):
    prep=part(h,"#[derive(Debug)]","\nimpl super::AgentRuntime")
    prep=prep.replace("#[derive(Debug)]","#[derive(Debug, PartialEq)]",1)
    prep=prep.replace("pub(crate) struct PreparedHistoryUpdate","pub(super) struct PreparedHistoryUpdate",1)
    prep=prep.replace("anyhow::bail!","bail!")
    uses="use std::borrow::Cow;\n" if "borrow::Cow" in h else ""
    compacted=part(refs["compacted"],"/// The accepted input stays immutable")
    compacted=compacted.replace(
        "    use crate::{\n        domain::CompactionUserMessageReplacement,\n        model_standard::{CanonicalPart, ContentPart, MessageRole, PartProvenance, PartScope},\n    };\n","")
    source_tests=part(h,"    fn changed_report()")
    native_tests="mod native_tests {\nuse super::*;\n"+source_tests
    exact_turn=part(t,"        let history_update = match prepare_","\n    async fn persist_current_user_message(")
    guard="pub(crate) fn prepare_failed_history_update(" in prep
    check(guard,"exact borrowed failed-history wrapper")
    return (f"mod {tag} {{\nuse super::*;\n"+uses+prep+"\nmod compacted_user {\nuse super::*;\n"+compacted+"}\n"
            +native_tests+EFFECTS+exact_turn+"}\n}\n")


STUB=r'''
#![allow(dead_code)]
use std::{alloc::{GlobalAlloc,Layout,System},cell::Cell,hint::black_box,path::PathBuf,
          collections::BTreeMap};

type MessageId=u128;
type PartId=u128;
thread_local! {
    static MESSAGE:Cell<u128>=const {Cell::new(1)};
    static PART:Cell<u128>=const {Cell::new(1)};
}
mod domain {
    pub(super) use super::{ImageRef,MessageId};
    pub fn new_message_id()->u128 {
        super::MESSAGE.with(|p| {let id=p.get();p.set(id+1);id})
    }
    pub fn new_part_id()->u128 {
        super::PART.with(|p| {let id=p.get();p.set(id+1);id})
    }
}
#[derive(Clone,Debug,PartialEq)]
pub struct ContextChunk {content:String}
#[derive(Clone,Debug,PartialEq)]
pub struct Patch {content:String}
type Citation=String;
#[derive(Clone,Debug,PartialEq)]
pub struct HostedToolActivity(String);
impl HostedToolActivity {
    fn kind(&self)->HostedKind {HostedKind}
}
struct HostedKind;
impl HostedKind {fn as_str(&self)->&'static str {"fixture"}}
mod serde_json {
    use super::{BTreeMap,HostedToolActivity};
    use std::{fmt::{self,Display},io::{self,Write}};
    #[derive(Clone,Debug,PartialEq)]
    pub enum Value {Null,Bool(bool),Number(i64),String(String),Array(Vec<Value>),Object(BTreeMap<String,Value>)}
    impl Display for Value {
        fn fmt(&self,f:&mut fmt::Formatter<'_>)->fmt::Result {
            // Inert fixture carrier, not JSON/Serde compatibility proof.
            write!(f,"{self:?}")
        }
    }
    pub fn to_writer(mut w:impl Write,value:&Value)->io::Result<()> {write!(&mut w,"{value}")}
    pub fn to_string(value:&HostedToolActivity)->io::Result<String> {Ok(value.0.clone())}
}
'''

MACRO=r'''
use std::{borrow::Cow,collections::HashSet};
type Result<T> = std::result::Result<T,String>;
macro_rules! bail {($($arg:tt)*)=>{return Err(format!($($arg)*))};}
macro_rules! ensure {($cond:expr,$($arg:tt)*)=>{if !$cond {bail!($($arg)*);}};}
'''

EFFECTS=r'''
pub(super) struct FakeRuntime {pub(super) effects:Vec<Effect>,pub(super) fail_commit:bool}
impl FakeRuntime {
    async fn fail_turn_preserving_steering(&mut self,turn_id:u128,error:String,delivery:&[u128])->Result<u32> {
        self.effects.push(Effect::Failed(turn_id,error.clone(),delivery.to_vec()));
        Err(error)
    }
    async fn commit_history_update(&mut self,turn_id:u128,update:PreparedHistoryUpdate,
        reports:&[HistoryCompactionReport],preserve:bool)->Result<()> {
        self.effects.push(Effect::Committed(turn_id,update.final_messages,update.replace,reports.to_vec(),preserve));
        if self.fail_commit {Err("fixture commit failure".into())} else {Ok(())}
    }
    pub(super) async fn terminal(&mut self,history:Vec<CanonicalMessage>,user_message:CanonicalMessage,
        workflow_output:WorkflowOutput,runtime_user_messages:HashSet<MessageId>,delivery_records:Vec<u128>)->Result<u32> {
        let turn_id=95;
'''

TESTS=r'''
#[derive(Debug,PartialEq,Clone)]
struct WorkflowOutput {
    new_messages:Vec<CanonicalMessage>,history_replacement:Option<Vec<CanonicalMessage>>,
    compactions:Vec<HistoryCompactionReport>,output:u32
}
#[derive(Debug,PartialEq)]
enum Effect { Failed(u128,String,Vec<u128>),Committed(u128,Vec<CanonicalMessage>,bool,Vec<HistoryCompactionReport>,bool) }
fn ready<T>(future:impl std::future::Future<Output=T>)->T {
    let mut fut=std::pin::pin!(future);
    let mut ctx=std::task::Context::from_waker(std::task::Waker::noop());
    match fut.as_mut().poll(&mut ctx) {std::task::Poll::Ready(out)=>out,_=>panic!("inert methods should be ready")}
}
fn msg(role:MessageRole,s:&str)->CanonicalMessage {CanonicalMessage::text(role,s)}
fn tool_result(s:&str)->CanonicalMessage {
    CanonicalMessage::new(MessageRole::Tool,vec![ContentPart::ToolResult{
        result:ToolResult::ok("inert call".into(),s)
    }])
}
fn derived(s:&str)->CanonicalMessage {
    CanonicalMessage::from_parts(MessageRole::User,
        vec![CanonicalPart::new(PartProvenance::Compactor,PartScope::Conversation,
                                ContentPart::Text{text:s.into()})])
}
fn report(items:&[(&CanonicalMessage,&CanonicalMessage)],changed:bool)->HistoryCompactionReport {
    let mut r=HistoryCompactionReport::unchanged(1,None);
    r.changed=changed;
    r.user_message_replacements=items.iter().map(|(old,new)|CompactionUserMessageReplacement{
        source_message_id:old.id,replacement_message_id:new.id}).collect();
    r
}
type Prepared=Result<(Vec<CanonicalMessage>,bool)>;
fn table(h:&[CanonicalMessage],u:&CanonicalMessage,s:&[CanonicalMessage],r:Option<&[CanonicalMessage]>,
         report:&[HistoryCompactionReport],permit:&HashSet<MessageId>)->Prepared {
    let a=stock::prepare_history_update(h,u,s,r,report,permit).map(|v|(v.final_messages,v.replace));
    let b=candidate::prepare_history_update(h,u,s,r,report,permit).map(|v|(v.final_messages,v.replace));
    let c=candidate::prepare_owned_history_update(h.to_vec(),u,s,r,report,permit).map(|v|(v.final_messages,v.replace));
    assert_eq!(a,b);assert_eq!(a,c);
    a
}
fn failed(h:&[CanonicalMessage],u:&CanonicalMessage,s:&[CanonicalMessage],r:Option<&[CanonicalMessage]>,
          report:&[HistoryCompactionReport],permit:&HashSet<MessageId>)->Prepared {
    let a=stock::prepare_failed_history_update(h,u,s,r,report,permit).map(|v|(v.final_messages,v.replace));
    let b=candidate::prepare_failed_history_update(h,u,s,r,report,permit).map(|v|(v.final_messages,v.replace));
    assert_eq!(a,b);a
}
const EMPTY:&str="workflow returned no new persistent turn messages";
const ANCHOR:&str="runtime history does not end with the persisted current user message";
const FAILED_EMPTY:&str="workflow failure returned an empty history update";
const MISSING:&str="workflow reported changed compaction without history replacement";
const SPURIOUS:&str="workflow returned history replacement without changed compaction";

#[test]
fn error_priority_and_exact_allowed_roles() {
    let u=msg(MessageRole::User,"persisted");
    let other=msg(MessageRole::User,"steering");
    let a=msg(MessageRole::Assistant,"answer");
    let no=HashSet::new();
    let changed=report(&[],true);
    assert_eq!(table(&[],&u,&[],None,&[changed.clone()],&no),Err(EMPTY.into()));
    assert_eq!(table(&[],&u,&[other.clone()],None,&[changed.clone()],&no),Err(ANCHOR.into()));
    let prefix=[u.clone()];
    let out=[a.clone(),other.clone()];
    assert_eq!(table(&prefix,&u,&out,None,&[changed.clone()],&no),
               Err("workflow new_messages[1] has non-persistent turn role User".into()));
    let permission=HashSet::from([other.id]);
    assert_eq!(table(&prefix,&u,&out,None,&[changed],&permission),Err(MISSING.into()));
    assert_eq!(table(&prefix,&u,&out,Some(&prefix),&[],&permission),Err(SPURIOUS.into()));
    assert_eq!(table(&prefix,&u,&out,None,&[],&permission),
               Ok((vec![u.clone(),a.clone(),other],false)));
    for r in [MessageRole::Developer,MessageRole::System] {
        assert_eq!(table(&prefix,&u,&[msg(r.clone(),"not legal")],None,&[],&no),
                   Err(format!("workflow new_messages[0] has non-persistent turn role {r:?}")));
    }
    assert_eq!(failed(&[],&u,&[],None,&[],&no),Err(FAILED_EMPTY.into()));
    assert_eq!(failed(&[],&u,&[],Some(&prefix),&[],&no),Err(ANCHOR.into()));
    assert_eq!(failed(&prefix,&u,&[],Some(&prefix),&[report(&[],true)],&no),Ok((prefix.to_vec(),true)));
}

#[test]
fn compacted_current_user_requires_exact_ids_and_ordered_reports() {
    let u=msg(MessageRole::User,"persisted");
    let x=derived("first");
    let y=derived("second");
    let mut altered=x.clone();
    altered.parts[0].scope=PartScope::Request;
    let a=msg(MessageRole::Assistant,"answer");
    let h=[u.clone()];
    let suffix=[a.clone()];
    let two=[report(&[(&u,&x)],true),report(&[(&x,&y)],true)];
    let no=HashSet::new();
    assert_eq!(table(&h,&u,&suffix,Some(&[y.clone()]),&two,&no),Ok((vec![y.clone(),a.clone()],true)));
    assert_eq!(table(&h,&u,&suffix,Some(&[y.clone()]),&[two[1].clone(),two[0].clone()],&no),
               Err("workflow history does not preserve the declared current user representation".into()));
    assert_eq!(table(&h,&u,&suffix,Some(&[u.clone(),y.clone()]),&two,&no),
               Err("workflow history retained an explicitly replaced current user message".into()));
    assert_eq!(table(&h,&u,&suffix,Some(&[altered]),&two[..1],&no),
               Err("workflow history does not preserve the declared current user representation".into()));
    assert_eq!(table(&h,&u,&suffix,Some(&[derived("persisted")]),&[report(&[],true)],&no),
               Err("workflow history replacement does not preserve the exact current user message".into()));
    assert_eq!(table(&h,&u,&suffix,Some(&[y.clone()]),&[report(&[(&u,&x),(&u,&y)],true)],&no),
               Err("compaction duplicated a replacement source".into()));
    assert_eq!(table(&h,&u,&suffix,Some(&[y.clone()]),&[report(&[(&u,&u)],true)],&no),
               Err("compaction replacement must have a fresh message identity".into()));
    assert_eq!(table(&h,&u,&suffix,Some(&[y.clone()]),&[report(&[(&u,&x)],false),two[1].clone()],&no),
               Err("unchanged compaction cannot replace user messages".into()));
}

#[test]
fn exact_terminal_call_hands_same_values_to_inert_commit_or_failed_steering() {
    let u=msg(MessageRole::User,"persisted");
    let a=msg(MessageRole::Assistant,"answer");
    let delivered=msg(MessageRole::User,"steering");
    let prior=msg(MessageRole::Assistant,"older");
    let rows=vec![prior.clone(),u.clone()];
    let no_replace=WorkflowOutput{new_messages:vec![a.clone(),delivered.clone()],
        history_replacement:None,compactions:vec![],output:71};
    let replacement=WorkflowOutput{new_messages:vec![a.clone()],history_replacement:Some(vec![u.clone()]),
        compactions:vec![report(&[],true)],output:71};
    for (out,commit_fails,exact) in [
        (no_replace.clone(),false,Ok(71)),
        (replacement,false,Ok(71)),
        (no_replace.clone(),true,Err("fixture commit failure".into())),
        (WorkflowOutput{new_messages:vec![],..no_replace.clone()},false,Err(EMPTY.into())),
    ]{
        let mut old=stock::FakeRuntime{effects:vec![],fail_commit:commit_fails};
        let mut new=candidate::FakeRuntime{effects:vec![],fail_commit:commit_fails};
        let permit=HashSet::from([delivered.id]);
        let x=ready(old.terminal(rows.clone(),u.clone(),out.clone(),permit.clone(),vec![delivered.id]));
        let y=ready(new.terminal(rows.clone(),u.clone(),out,permit,vec![delivered.id]));
        assert_eq!((x,&old.effects),(y.clone(),&new.effects));
        assert_eq!(y,exact);
        assert_eq!(new.effects.len(),1);
        if exact==Err(EMPTY.into()) {
            assert_eq!(new.effects,[Effect::Failed(95,EMPTY.into(),vec![delivered.id])]);
        } else {
            assert!(matches!(&new.effects[0],Effect::Committed(95,_,_,_,false)));
        }
    }
}

#[test]
fn generated_owned_and_borrowed_outcomes_match_over_guard_matrix() {
    let mut seed=577_129_u64;
    let mut next=|n:usize|{seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);(seed>>32)as usize%n};
    for _ in 0..4096 {
        let u=msg(MessageRole::User,"user");
        let x=derived("replacement");
        let y=derived("second");
        let mut h=vec![msg(MessageRole::Assistant,"history"),u.clone()];
        if next(4)==0{h.push(msg(MessageRole::User,"mismatch"));}
        let s=(0..next(5)).map(|_|match next(5){
            0=>msg(MessageRole::User,"steering"),1=>msg(MessageRole::Developer,"system"),
            2=>tool_result("tool fixture"),_=>msg(MessageRole::Assistant,"reply"),
        }).collect::<Vec<_>>();
        let permitted=s.iter().filter(|m|m.role==MessageRole::User&&next(2)==0)
            .map(|m|m.id).collect::<HashSet<_>>();
        let r=match next(4){0=>None,1=>Some(vec![]),2=>Some(vec![u.clone(),x.clone()]),_=>Some(vec![y.clone()])};
        let reports=match next(5){
            0=>vec![],1=>vec![report(&[],true)],2=>vec![report(&[(&u,&x)],true)],
            3=>vec![report(&[(&u,&x)],true),report(&[(&x,&y)],true)],
            _=>vec![report(&[(&u,&x)],false)]
        };
        let _=table(&h,&u,&s,r.as_deref(),&reports,&permitted);
        let _=failed(&h,&u,&s,r.as_deref(),&reports,&permitted);
    }
}

const TEXT:usize=262_151;
const TOOL:usize=131_071;
#[derive(Debug,Default,Clone,Copy,PartialEq,Eq)]
struct Stats { alloc:usize,realloc:usize,bytes:usize,text:usize,tool:usize }
thread_local!{static METER:Cell<Option<Stats>>=const{Cell::new(None)};}
fn count(n:usize,re:bool) {
    let _=METER.try_with(|m|if let Some(mut s)=m.get(){
        if re{s.realloc+=1;}else{s.alloc+=1;}
        s.bytes+=n;
        if n==TEXT{s.text+=1;}
        if n==TOOL{s.tool+=1;}
        m.set(Some(s));
    });
}
struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self,l:Layout)->*mut u8{count(l.size(),false);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{count(l.size(),false);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{count(n,true);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
}
#[global_allocator] static ALLOCATOR:Meter=Meter;
fn measure<T>(f:impl FnOnce()->T)->(T,Stats){
    assert!(METER.replace(Some(Stats::default())).is_none());
    let out=black_box(f());
    (out,METER.take().unwrap())
}
fn payload(m:&CanonicalMessage)->usize {
    match &m.parts[0].payload {
        ContentPart::Text{text}=>text.as_ptr() as usize,
        ContentPart::ToolResult{result}=>result.output.as_ptr() as usize,
        _=>unreachable!(),
    }
}
#[test]
fn unchanged_owned_success_reuses_payloads_reserves_exact_and_keeps_original_slack() {
    let u=msg(MessageRole::User,"persisted");
    let mut large=msg(MessageRole::Assistant,&"x".repeat(TEXT));
    large.name=Some("untouched envelope".into());
    let rows=vec![large,tool_result(&"y".repeat(TOOL)),u.clone()];
    let out=[msg(MessageRole::Assistant,"new")];
    let permitted=HashSet::new();
    let on_exact=rows.clone();
    assert_eq!(on_exact.capacity(),on_exact.len());
    let old_payload=[payload(&on_exact[0]),payload(&on_exact[1])];
    let (a,x)=measure(||stock::prepare_history_update(black_box(&rows),&u,&out,None,&[],&permitted).unwrap());
    let (b,z)=measure(||candidate::prepare_history_update(black_box(&rows),&u,&out,None,&[],&permitted).unwrap());
    let (c,y)=measure(||candidate::prepare_owned_history_update(black_box(on_exact),&u,&out,None,&[],&permitted).unwrap());
    assert_eq!(a.final_messages,b.final_messages);
    assert_eq!(a.final_messages,c.final_messages);
    assert_eq!(x,z);
    assert_eq!((x.text,x.tool),(1,1));
    assert_eq!((y.text,y.tool),(0,0));
    assert_eq!([payload(&c.final_messages[0]),payload(&c.final_messages[1])],old_payload);
    assert_ne!(payload(&c.final_messages[3]),payload(&out[0]));
    assert_eq!((a.final_messages.capacity(),b.final_messages.capacity(),c.final_messages.capacity()),(4,4,4));
    let mut slack=Vec::with_capacity(128);slack.extend_from_slice(&rows);
    let used=payload(&slack[0]);
    let (d,v)=measure(||candidate::prepare_owned_history_update(black_box(slack),&u,&out,None,&[],&permitted).unwrap());
    assert_eq!(d.final_messages.capacity(),128);
    assert_eq!(d.final_messages,c.final_messages);
    assert_eq!(payload(&d.final_messages[0]),used);
    assert_eq!(v.realloc,0);
    println!("R256_ALLOC {} {} {} {} {} {} {} {} {} {} {}",
        x.alloc,x.realloc,x.bytes,y.alloc,y.realloc,y.bytes,v.alloc,v.realloc,v.bytes,
        c.final_messages.capacity(),d.final_messages.capacity());
}
#[test]
fn failed_guard_precedes_allocation_and_replacement_keeps_old_copy_shape() {
    let u=msg(MessageRole::User,"persisted");
    let a=msg(MessageRole::Assistant,"answer");
    let no=HashSet::new();
    let rows=vec![u.clone()];
    let old_h=rows.clone();
    let (err,s)=measure(||candidate::prepare_owned_history_update(old_h,&u,&[],None,&[],&no).unwrap_err());
    assert_eq!(err,EMPTY);
    // Only the error string is allocated; no capacity reservation or prefix clones.
    assert_eq!(s.realloc,0);
    assert_eq!(s.alloc,1);
    let suffix=[a];
    let rep=[u.clone(),derived("summary")];
    let changed=[report(&[],true)];
    let h=rows.clone();
    let a=measure(||stock::prepare_history_update(&rows,&u,&suffix,Some(&rep),&changed,&no).unwrap());
    let b=measure(||candidate::prepare_owned_history_update(h,&u,&suffix,Some(&rep),&changed,&no).unwrap());
    assert_eq!(a.0.final_messages,b.0.final_messages);
    assert_eq!(a.1,b.1);
    assert!(b.0.replace);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("refs","work","rustc"):
        parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--git",type=Path,default=Path("/usr/bin/git"))
    args=parser.parse_args()
    packet=Path(__file__).parent
    meta=json.loads((packet/"SOURCE-PROVENANCE.json").read_text())
    refs={}
    for k,descriptor in meta["reproduction_inputs"].items():
        refs[k]=(args.refs/(k+".ref")).read_bytes()
        pin(refs[k],descriptor,k)
    rustc=args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC_SHA,"compiler pin")
    with tempfile.TemporaryDirectory(prefix="r256-",dir=args.work.resolve(strict=True)) as tmp:
        root=Path(tmp)
        env={"PATH":"/usr/bin:/bin","HOME":tmp,"TMPDIR":tmp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        changed=verify_git(root,env,args.git.resolve(strict=True),refs,packet,meta)
        text={k:v.decode() for k,v in refs.items()}
        check("pub(crate) use history::{prepare_failed_history_update, prepare_history_update};" in text["runtime"]
              and "UserMessageReservationAttempt, prepare_failed_history_update, prepare_history_update," in text["core"],
              "same borrowed reexports")
        for key,names in [("replay",("prepare_history_update(","prepare_failed_history_update(")),
                          ("checkpoint",("prepare_failed_history_update(",)),("failed",("prepare_failed_history_update(",))]:
            check(all(n in text[key] for n in names),"pinned borrowed consumer "+key)
        validate=part(text["validation"],"pub fn is_compacted_user_message(","pub fn validate_context_preparation_output(")
        code=STUB+MACRO+contract(text)+validate
        code+=variant("stock",text["history"],text["turn"],text)
        code+=variant("candidate",changed["history"].decode(),changed["turn"].decode(),text)
        code+=TESTS
        unit=root/"lift.rs";unit.write_text(code,encoding="utf-8")
        proof={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,"-o",exe],
                           cwd=root,env=env,check=True,timeout=90)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,capture_output=True,
                               text=True,timeout=90)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 18 passed; 0 failed;" in out.stdout,"test count")
            m=re.search(r"(?m)\bR256_ALLOC ((?:\d+ ){10}\d+)$",out.stdout)
            check(m is not None,"allocation receipt")
            n=list(map(int,m[1].split()))
            proof[mode]=dict(tests_passed=18,generated_three_arm_cases=4096,
                     stock_alloc_realloc_requested_bytes=n[:3],owned_exact_alloc_realloc_requested_bytes=n[3:6],
                     owned_slack_alloc_realloc_requested_bytes=n[6:9],owned_final_capacity_exact_and_slack=n[9:])
    print(json.dumps(dict(status="PASS",rustc=version,rustc_sha256=RUSTC_SHA,
                          exact_patch_roundtrip=True,actual_storage_runtime_serde=False,results=proof),indent=2))


if __name__=="__main__":
    main()
