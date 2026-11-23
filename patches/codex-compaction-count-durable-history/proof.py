#!/usr/bin/env python3
"""Verify scoped count-only Codex compaction with real lifted selector and both routes."""
import argparse
from difflib import unified_diff
import hashlib
from itertools import permutations
import json
from pathlib import Path
import re
import subprocess
import tempfile

SOURCE="hook/codex-context-preparation/src"
CORE="0c1b7572313230e5d123e95c722e1258a2e9ecd6"
RUSTC_SHA="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION="rustc 1.95.0 (59807616e 2026-04-14)"
FILES=("budget","compaction","history","remote","remote_history")
PRIORS=(517,521,562,563)


def check(ok,label):
    if not ok:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def ident(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest(),sha(raw)


def pin(raw,expected,label):
    check(ident(raw)==(expected["git_blob"],expected["sha256"]),f"identity: {label}")


def part(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]


def serde_free(s):
    return re.sub(r"(?m)^#\[serde\([^\n]+\)\]\n","",s).replace(", Serialize, Deserialize","")


def patch_between(before,after):
    result=b""
    for key in sorted(before):
        a,b=before[key],after[key]
        if a==b:
            continue
        path=f"{SOURCE}/{key}.rs"
        result+=(f"diff --git a/{path} b/{path}\nindex {ident(a)[0]}..{ident(b)[0]} 100644\n"
                 +"".join(unified_diff(a.decode().splitlines(keepends=True),
                                       b.decode().splitlines(keepends=True),"a/"+path,"b/"+path))).encode()
    return result


def effects(patch):
    return [[line for line in file.splitlines()
             if line[:1] in (b"+",b"-") and not line.startswith((b"+++ ",b"--- "))]
            for file in patch.split(b"diff --git ")[1:]]


def verify_git(home,env,git,meta,refs):
    dst=home/SOURCE
    dst.mkdir(parents=True)
    originals={k:refs[k] for k in FILES}
    packet=Path(__file__).parent
    files={n:home/f"{n}.patch" for n in (*PRIORS,255,1255,1563)}
    config=env | {"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
                  "GIT_CEILING_DIRECTORIES":str(home.parent)}
    for n in PRIORS:
        files[n].write_bytes(refs[f"prior-{n}"])
    for n,name in ((255,"source.patch"),(1255,"composed.patch")):
        b=(packet/name).read_bytes()
        pin(b,meta["patches"][name],name)
        files[n].write_bytes(b)
    check(effects(files[255].read_bytes())==effects(files[1255].read_bytes()),
          "R255 after #563 changes exact same lines")
    def read():
        return {k:(dst/f"{k}.rs").read_bytes() for k in FILES}
    def reset():
        for k,b in originals.items():
            (dst/f"{k}.rs").write_bytes(b)
    def state(name):
        d=read()
        for k,v in d.items():
            pin(v,meta["identities"][name][k],f"{name}/{k}")
        return d
    def act(n,reverse=False):
        switches=["-R"] if reverse else []
        for phase in (["--check"],[]):
            subprocess.run([git,"apply",*switches,*phase,files[n]],cwd=home,env=config,
                           check=True,timeout=20,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def blocked(n):
        r=subprocess.run([git,"apply","--check",files[n]],cwd=home,env=config,
                         capture_output=True,timeout=20)
        check(r.returncode!=0 and b"patch failed: "+SOURCE.encode()+b"/compaction.rs:" in r.stderr,
              "expected adjacent normal-Git conflict")
    reset();act(255);candidate=state("standalone");blocked(563);act(255,True)
    check(read()==originals,"standalone rollback")
    act(563);state("only563");blocked(255);act(1255);both=state("both255563")
    carry=patch_between(candidate,both)
    check(effects(carry)==effects(refs["prior-563"]),"inverse order #563 exact changes")
    pin(carry,meta["patches"]["derived-carry-563"],"derived #563 carry")
    files[1563].write_bytes(carry)
    act(1255,True);state("only563");act(563,True)
    check(read()==originals,"two-patch rollback")
    for n in PRIORS:
        act(n)
    prior=state("prior")
    for n in reversed(PRIORS):
        act(n,True)
    check(read()==originals,"prior rollback")
    for order in permutations((*PRIORS,255)):
        states=[read()]
        used=[]
        for n in order:
            carrier=1255 if n==255 and 563 in used else 1563 if n==563 and 255 in used else n
            used.append(n)
            act(carrier)
            states.append((read(),carrier))
        combined=state("combined")
        sources=[states[0],*(d for d,_ in states[1:])]
        for i in range(len(order),0,-1):
            act(states[i][1],True)
            check(read()==sources[i-1],"all intermediate bytes reverse exactly")
    return dict(stock=originals,candidate=candidate,prior=prior,composed=combined)


def exact_output(r):
    s=r["sdk-output"]
    dto=part(s,"pub struct ContextPreparationOutput {","/// Diagnostics for an unchanged")
    ctor=part(s,"    pub fn changed(messages: Vec<CanonicalMessage>","\nimpl HistoryCompactionReport")
    return "#[derive(Debug,Clone,PartialEq)]\n"+dto+"\nimpl ContextPreparationOutput {\n"+ctor


def prep_variant(name,files,tests):
    h,b,c,r,rh=[files[k].decode() for k in ("history","budget","compaction","remote","remote_history")]
    new="compactable_message_count" in h
    history=part(h,"pub(crate) struct HistoryParts").replace("crate::budget::estimate_text_tokens","estimate_text_tokens")
    if "use std::borrow::Cow;" in h:
        history="use std::borrow::Cow;\n"+history
    history="use crate::domain::new_message_id;\n"+history
    budget=part(b,"const DEFAULT_USER_MESSAGE_BUDGET_TOKENS","/// Mirrors the pinned Codex")+part(b,"pub(crate) fn user_message_budget_tokens(")
    local=part(c,"    let unchanged = |mut output", "    let Some(trigger_tokens)") + part(c,"    let history = split_history")
    local=local.replace("crate::remote::compact(","remote_compact(")
    local=local.replace("proteus_contracts::model_standard::CanonicalMessage","CanonicalMessage")
    remote=part(r,"pub(crate) fn compact(","\nfn request(").replace("pub(crate) fn compact(","fn remote_compact(",1)
    remote=remote.replace("crate::input_estimates::for_messages","fixture_estimates")
    remote_history=part(rh,"const AUTO_IMAGE_TOKENS")
    count="history.compactable_message_count" if new else "history.compactable_history.len()"
    users="collect_user_messages(rows)" if new else "collect_user_messages(&history.compactable_history)"
    if "ToolContent, new_message_id" not in rh:
        # Local history still imports the stub ID for its unchanged selector.
        check("CanonicalMessage::from_parts(message.role.clone(), parts)" in rh,"exact #562 adoption in prior arms")
    basetests=part(tests,"#[test]\nfn compacted_image_users_match_upstream_text_only_reconstruction","\nuse crate::{\n    budget::")
    basetests=basetests.replace("    use proteus_contracts::domain::ImageRef;\n","").replace("crate::history::","")
    return (f"#[allow(unreachable_patterns)]\nmod {name} {{\nuse super::*;\n"+history+budget+remote_history+remote
            +"pub(super) fn run(rows:&[CanonicalMessage],remote:bool,host:&mut dyn HookModuleHost)->Result<ContextPreparationOutput,ProcessModuleError>{\n"
             "    let input=ContextPreparationInput{messages:rows.to_vec(),request:Some(Template{model:()})};\n"
             "    let config=&CompactorConfig; let estimates=ModelInputEstimate; let token_estimate=41;let trigger_tokens=7;\n"
            +local
            +"pub(super) fn partition(rows:&[CanonicalMessage])->PartResult{\n"
            +"    let history=split_history(rows);\n"
            +f"    let n={count};\n    let users={users};\n"
             "    PartResult{n,users,summary:history.summary_history,ephemeral:history.ephemeral_context}\n}\n"
            +"pub(super) fn sample(rows:&[CanonicalMessage])->(usize,Vec<CanonicalMessage>,Vec<CanonicalMessage>,Stats){\n"
             "    assert!(METER.replace(Some(Stats::default())).is_none());\n"
             "    let history=black_box(split_history(black_box(rows)));\n"
             "    let stats=METER.take().unwrap();\n"
            +f"    ({count},history.summary_history,history.ephemeral_context,stats)\n}}\n"
            +basetests+"}\n")


def contract(r):
    s=r["content"]
    t=r["tool"]
    roles=part(s,"#[derive(Debug, Clone, Serialize","\nimpl CanonicalMessage")
    funcs=("impl CanonicalMessage {\n"
           +part(s,"    pub fn display_text(","    /// Readable reasoning")
           +part(s,"    pub fn text(role: MessageRole","    pub fn with_id(mut self, id: MessageId)")
           +"}\n"+part(s,"fn default_part_semantics(","#[cfg(test)]"))
    alias=re.search(r"(?m)^pub type CallId = String;$",r["ids"])[0]+"\n"
    call=("#[derive(Debug,Clone,PartialEq)]\n"+part(t,"pub struct ToolCall {","    pub fn with_surface(")+"}\n"
          +"#[derive(Debug,Clone,Copy,PartialEq,Eq,Default)]\n"+part(t,"pub enum ToolCallSurface {","impl ToolCallSurface"))
    result=("#[derive(Debug,Clone,PartialEq)]\n"+part(t,"pub struct ToolResult {","#[cfg(test)]"))
    replace=("#[derive(Debug,Clone,PartialEq)]\n"
             +part(r["sdk-map"],"pub struct CompactionUserMessageReplacement {","\n}\n")+"\n}\n")
    image=("#[derive(Debug,Clone,PartialEq,Eq)]\n"
           +part(r["sdk-image"],"pub struct ImageRef {","\n}\n")+"\n}\n")
    msg=part(roles,"pub struct CanonicalMessage {","\n}\n")
    fields=re.findall(r"(?m)^    pub (\w+):",msg)
    check(fields==["id","role","phase","parts","name","tool_call_id","metadata"],"every pinned envelope field")
    check(funcs.count("id: crate::domain::new_message_id()")==1,"one identity from actual constructor")
    return serde_free(alias+call+result+replace+image+roles+funcs)


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

CONTEXT=r'''
use serde_json::Value;
macro_rules! json {
    ({$($key:literal: $value:expr),+ $(,)?}) => {
        Value::Object(BTreeMap::from([$(($key.into(),datum($value))),+]))
    };
}
fn datum<T:IntoDatum>(value:T)->Value { value.datum() }
trait IntoDatum {fn datum(self)->Value;}
impl IntoDatum for usize {fn datum(self)->Value {Value::Number(self as i64)}}
impl IntoDatum for bool {fn datum(self)->Value {Value::Bool(self)}}
#[derive(Debug,Clone,PartialEq,Eq)]
enum ProcessModuleError { Failed, Cancelled }
struct Template {model:()}
struct ContextPreparationInput {messages:Vec<CanonicalMessage>,request:Option<Template>}
struct CompactorConfig;
#[derive(Default)]
struct ModelInputEstimate;
impl ModelInputEstimate {
    fn tokens_for(&self,_:&CanonicalPart)->Option<u32> {None}
    fn write_metadata(&self,_:&mut Value) {}
}
#[derive(Clone,Copy)]
enum Outcome { Ok, Error, Cancel }
struct Host {outcome:Outcome,seen:Vec<(bool,Vec<MessageId>)>}
trait HookModuleHost {
    fn seen(&mut self,remote:bool,ids:Vec<MessageId>);
    fn outcome(&self)->Outcome;
}
impl HookModuleHost for Host {
    fn seen(&mut self,remote:bool,ids:Vec<MessageId>) {self.seen.push((remote,ids));}
    fn outcome(&self)->Outcome {self.outcome}
}
fn complete_summary_with_recovery(_: &ContextPreparationInput,_:&CompactorConfig,
    summary:Vec<CanonicalMessage>,host:&mut dyn HookModuleHost)->Result<String,ProcessModuleError>{
    host.seen(false,summary.iter().map(|m|m.id).collect());
    match host.outcome() {
        Outcome::Ok=>Ok("fixture summary".into()), Outcome::Error=>Err(ProcessModuleError::Failed),
        Outcome::Cancel=>Err(ProcessModuleError::Cancelled),
    }
}
struct RemoteRequest(Vec<CanonicalMessage>);
fn request(_: &ContextPreparationInput,history:Vec<CanonicalMessage>,_:&ModelInputEstimate)
    ->Result<RemoteRequest,ProcessModuleError> {Ok(RemoteRequest(history))}
fn complete_checkpoint(request:RemoteRequest,_:&CompactorConfig,host:&mut dyn HookModuleHost)
    ->Result<CanonicalMessage,ProcessModuleError>{
    host.seen(true,request.0.iter().map(|m|m.id).collect());
    if matches!(host.outcome(),Outcome::Error) {return Err(ProcessModuleError::Failed);}
    Ok(CanonicalMessage::text(MessageRole::Assistant,"inert checkpoint"))
}
fn ensure_not_cancelled(host:&mut dyn HookModuleHost)->Result<(),ProcessModuleError> {
    if matches!(host.outcome(),Outcome::Cancel) {Err(ProcessModuleError::Cancelled)} else {Ok(())}
}
fn fixture_estimates(_: &(),_: &[CanonicalMessage],_:&mut dyn HookModuleHost)
    ->Result<ModelInputEstimate,ProcessModuleError> {Ok(ModelInputEstimate)}
'''

TESTS=r'''
#[derive(PartialEq,Debug)]
struct PartResult {n:usize,users:Vec<CanonicalMessage>,summary:Vec<CanonicalMessage>,ephemeral:Vec<CanonicalMessage>}
type Run=fn(&[CanonicalMessage],bool,&mut dyn HookModuleHost)->Result<ContextPreparationOutput,ProcessModuleError>;
type Partition=fn(&[CanonicalMessage])->PartResult;
const RUN:[Run;4]=[stock::run,candidate::run,prior::run,composed::run];
const PARTITION:[Partition;4]=[stock::partition,candidate::partition,prior::partition,composed::partition];
fn text(role:MessageRole,s:&str)->CanonicalMessage {CanonicalMessage::text(role,s)}
fn user(s:&str)->CanonicalMessage {text(MessageRole::User,s)}
fn req(mut m:CanonicalMessage)->CanonicalMessage {
    for p in &mut m.parts{p.scope=PartScope::Request;}
    m
}
fn call(scope:PartScope)->CanonicalMessage {
    let mut m=CanonicalMessage::new(MessageRole::Assistant,
        vec![ContentPart::ToolCall{call:ToolCall::new("fixture","inert",Value::Null)}]);
    m.parts[0].scope=scope;m
}
fn result(out:&str,scope:PartScope)->CanonicalMessage {
    let mut m=CanonicalMessage::new(MessageRole::Tool,
        vec![ContentPart::ToolResult{result:ToolResult::ok("fixture".into(),out)}]);
    m.parts[0].scope=scope;m
}
fn picture()->ContentPart {
    ContentPart::Image{image:ImageRef{id:"fixture".into(),name:"fixture.png".into(),
                                    mime_type:"image/png".into(),path:"inert".into()}}
}
fn metadata(out:&ContextPreparationOutput,key:&str)->i64 {
    match &out.metadata {Value::Object(m)=>{let Value::Number(n)=m[key] else {panic!()};n}, _=>panic!()}
}
fn checked_partition(rows:&[CanonicalMessage])->PartResult {
    let first=PARTITION[0](rows);
    for f in &PARTITION[1..] {assert_eq!(f(rows),first);}
    assert_eq!(first.summary,rows);
    first
}
fn checked_routes(rows:&[CanonicalMessage],remote:bool,outcome:Outcome)->(Result<ContextPreparationOutput,ProcessModuleError>,Vec<(bool,Vec<MessageId>)>) {
    let each=|f:Run|{
        MESSAGE.set(1_000_000);PART.set(2_000_000);
        let mut host=Host{outcome,seen:vec![]};
        let res=f(rows,remote,&mut host);
        (res,host.seen,MESSAGE.get(),PART.get())
    };
    let first=each(RUN[0]);
    for f in &RUN[1..] {assert_eq!(each(*f),first);}
    (first.0,first.1)
}

#[test]
fn no_durable_is_unchanged_without_host_even_if_request_scoped_tool_pair() {
    let input=[req(user("all request")),call(PartScope::Request),result("ephemeral pair",PartScope::Request)];
    let selected=checked_partition(&input);
    assert_eq!(selected.n,0);
    assert!(selected.users.is_empty());
    assert_eq!(selected.ephemeral,&input[..1]);
    for remote in [false,true] {
        let (out,seen)=checked_routes(&input,remote,Outcome::Error);
        assert!(seen.is_empty());
        let out=out.unwrap();
        assert!(!out.changed);
        assert_eq!(out.messages,input);
        assert_eq!(out.skipped_reason.as_deref(),Some("no_persistent_history_to_compact"));
        assert_eq!(out.original_token_estimate,Some(41));
        assert_eq!(out.token_estimate,Some(41));
        assert_eq!(out.trigger_tokens,Some(7));
        assert_eq!(out.metadata,Value::Null);
    }
}

#[test]
fn durable_without_users_still_compacts_and_counts_empty_part_rows() {
    let empty=CanonicalMessage::new(MessageRole::User,vec![]);
    let input=[req(text(MessageRole::Developer,"context")),text(MessageRole::Assistant,"answer"),
               result("durable",PartScope::Conversation),empty];
    let selected=checked_partition(&input);
    assert_eq!(selected.n,3);
    assert!(selected.users.is_empty());
    for remote in [false,true] {
        let (out,seen)=checked_routes(&input,remote,Outcome::Ok);
        assert_eq!(seen,vec![(remote,input.iter().map(|m|m.id).collect())]);
        let out=out.unwrap();
        assert!(out.changed);
        assert_eq!(metadata(&out,"compacted_messages"),3);
        assert_eq!(metadata(&out,"preserved_user_messages"),0);
        assert_eq!(metadata(&out,"ephemeral_context_messages"),1);
        assert_eq!(out.messages.len(),2);
        assert_eq!(out.messages[0],input[0]);
        assert_ne!(out.messages[1].id,input[0].id);
        assert!(out.user_message_replacements.is_empty());
    }
}

#[test]
fn all_request_vs_mixed_trace_markers_image_anchors_and_duplicate_ids() {
    let mut old=user("ordinary");
    old.phase=Some(MessagePhase::FinalAnswer);
    old.name=Some("名".into());old.tool_call_id=Some("opaque!".into());
    old.metadata=Value::Array(vec![Value::Null,Value::String("value".into())]);
    let mut mixed=CanonicalMessage::new(MessageRole::User,vec![ContentPart::Text{text:"work".into()},picture()]);
    mixed.parts[0].scope=PartScope::Request;
    let mut traced=user("trace still durable");traced.parts[0].scope=PartScope::Trace;
    let photo=CanonicalMessage::new(MessageRole::User,vec![picture()]);
    let both_generated=CanonicalMessage::new(MessageRole::User,vec![
            ContentPart::Text{text:"<turn_aborted> plus an image".into()},picture()]);
    let input=vec![
        old.clone(),req(user("request")),mixed.clone(),traced.clone(),
        user("<turn_aborted> suppressed"),user(&format!("{SUMMARY_PREFIX}\nold")),
        req(user("<turn_aborted> request only")),req(photo.clone()),
        photo.clone(),both_generated.clone(),old.clone(),user(""),
        call(PartScope::Request),result("request",PartScope::Request),
    ];
    let a=checked_partition(&input);
    assert_eq!(a.n,9);
    assert_eq!(a.users,vec![old.clone(),mixed,traced,photo,both_generated,old,input[11].clone()]);
    assert_eq!(a.ephemeral,vec![input[1].clone(),input[6].clone(),input[7].clone()]);
    for remote in [false,true] {
        let (out,seen)=checked_routes(&input,remote,Outcome::Ok);
        assert_eq!(seen.len(),1);
        let out=out.unwrap();
        assert_eq!(metadata(&out,"compacted_messages"),9);
        assert_eq!(metadata(&out,"preserved_user_messages"),7);
        assert_eq!(metadata(&out,"ephemeral_context_messages"),3);
        assert_eq!(out.messages.len(),11);
    }
}

#[test]
fn errors_and_cancellation_return_same_exact_status_in_both_routes() {
    let rows=[req(user("context")),user("previous"),result("tool",PartScope::Conversation)];
    for remote in [false,true] {
        for (test,want) in [(Outcome::Error,ProcessModuleError::Failed),(Outcome::Cancel,ProcessModuleError::Cancelled)] {
            let (out,seen)=checked_routes(&rows,remote,test);
            assert_eq!(out,Err(want));
            assert_eq!(seen,vec![(remote,rows.iter().map(|m|m.id).collect())]);
        }
    }
}

#[test]
fn generated_four_arm_partition_and_both_routes() {
    let mut rng=453_877_u64;
    let mut next=|n:usize| {rng=rng.wrapping_mul(6364136223846793005).wrapping_add(1);(rng>>32) as usize%n};
    for _ in 0..4096 {
        let mut rows=vec![];
        for _ in 0..1+next(12) {
            let mut row=match next(10) {
                0=>user("old"),1=>user(""),2=>user("<turn_aborted> x"),3=>text(MessageRole::System,"system"),
                4=>CanonicalMessage::new(MessageRole::User,vec![picture()]),5=>text(MessageRole::Developer,"context"),
                6=>call(PartScope::Conversation),7=>result("工具",PartScope::Conversation),
                8=>CanonicalMessage::new(MessageRole::Assistant,vec![]),
                _=>CanonicalMessage::new(MessageRole::User,vec![picture(),ContentPart::Text{text:"latest".into()}])
            };
            for p in &mut row.parts {p.scope=[PartScope::Conversation,PartScope::Request,PartScope::Trace][next(3)];}
            rows.push(row);
        }
        let _=checked_partition(&rows);
        let _=checked_routes(&rows,false,Outcome::Ok);
        let _=checked_routes(&rows,true,Outcome::Ok);
    }
}

const TEXT_BYTES:usize=131_072;
const TOOL_BYTES:usize=262_151;
const EPHEMERAL_BYTES:usize=4093;
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Stats {alloc:usize,realloc:usize,bytes:usize,text:usize,tool:usize,ephemeral:usize}
thread_local!{static METER:Cell<Option<Stats>>=const{Cell::new(None)};}
fn count(n:usize,re:bool){
    let _=METER.try_with(|m|if let Some(mut s)=m.get(){
        if re{s.realloc+=1;}else{s.alloc+=1;}
        s.bytes+=n;
        if n==TEXT_BYTES {s.text+=1;}
        if n==TOOL_BYTES {s.tool+=1;}
        if n==EPHEMERAL_BYTES {s.ephemeral+=1;}
        m.set(Some(s));
    });
}
struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {count(l.size(),false);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {count(l.size(),false);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {count(n,true);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
}
#[global_allocator] static ALLOCATOR:Meter=Meter;
#[test]
fn scoped_split_clone_layouts_text_tool_and_unchanged_ephemeral() {
    let rows=[
        text(MessageRole::Assistant,&"a".repeat(TEXT_BYTES)),
        result(&"b".repeat(TOOL_BYTES),PartScope::Conversation),
        req(text(MessageRole::Developer,&"c".repeat(EPHEMERAL_BYTES))),
    ];
    type Sample=fn(&[CanonicalMessage])->(usize,Vec<CanonicalMessage>,Vec<CanonicalMessage>,Stats);
    for (label,a,b) in [("stock",stock::sample as Sample,candidate::sample as Sample),
                        ("composed",prior::sample as Sample,composed::sample as Sample)] {
        let (old_n,old_summary,old_ephemeral,x)=a(&rows);
        let (new_n,new_summary,new_ephemeral,y)=b(&rows);
        assert_eq!((old_n,new_n),(2,2));
        assert_eq!(old_summary,rows);assert_eq!(new_summary,rows);
        assert_eq!(old_ephemeral,&rows[2..]);assert_eq!(new_ephemeral,old_ephemeral);
        assert_eq!((x.text,x.tool,x.ephemeral),(2,2,2));
        assert_eq!((y.text,y.tool,y.ephemeral),(1,1,2));
        assert!(x.alloc-y.alloc>=3);assert!(x.bytes-y.bytes>=TEXT_BYTES+TOOL_BYTES);
        println!("R255_ALLOC {label} {} {} {} {} {} {}",x.alloc,x.realloc,x.bytes,y.alloc,y.realloc,y.bytes);
    }
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("refs","work","rustc"):
        parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--git",type=Path,default=Path("/usr/bin/git"))
    args=parser.parse_args()
    meta=json.loads(Path(__file__).with_name("SOURCE-PROVENANCE.json").read_text())
    refs={}
    for key,p in meta["reproduction_inputs"].items():
        refs[key]=(args.refs/(key+".ref")).read_bytes()
        pin(refs[key],p,key)
    lock=next(x for x in refs["lock"].decode().split("[[package]]") if '\nname = "proteus-contracts"\n' in x)
    check(f"?rev={CORE}#{CORE}" in lock,"locked sdk")
    rustc=args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC_SHA,"compiler identity")
    with tempfile.TemporaryDirectory(prefix="r255-",dir=args.work.resolve(strict=True)) as tmp:
        home=Path(tmp)
        env={"PATH":"/usr/bin:/bin","HOME":tmp,"TMPDIR":tmp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=home,env=env,text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        arms=verify_git(home,env,args.git.resolve(strict=True),meta,refs)
        strings={k:b.decode() for k,b in refs.items()}
        code=STUB+CONTEXT+contract(strings)+exact_output(strings)+"\nconst SUMMARY_PREFIX:&str="+json.dumps(strings["prefix"],ensure_ascii=False)+";\n"
        code+="".join(prep_variant(k,v,strings["tests"]) for k,v in arms.items())+TESTS
        unit=home/"lift.rs";unit.write_text(code,encoding="utf-8")
        results={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=home/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,"-o",exe],
                           check=True,cwd=home,env=env,timeout=90)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=home,env=env,text=True,
                               capture_output=True,timeout=90)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 14 passed; 0 failed;" in out.stdout,"exact test count")
            seen={}
            for k,v in re.findall(r"(?m)\bR255_ALLOC (\w+) ((?:\d+ ){5}\d+)$",out.stdout):
                n=list(map(int,v.split()))
                seen[k]=dict(stock_alloc_realloc_requested_bytes=n[:3],candidate_alloc_realloc_requested_bytes=n[3:])
            check(set(seen)=={"stock","composed"},"allocation receipts")
            results[mode]=dict(tests_passed=14,generated_four_arm_both_route_cases=4096,allocations=seen)
    print(json.dumps(dict(status="PASS",rustc=version,rustc_sha256=RUSTC_SHA,
                          locked_core=CORE,composed_routes_and_exact_reversals=120,
                          actual_provider_serde_db_or_app=False,results=results),indent=2))


if __name__=="__main__":
    main()
