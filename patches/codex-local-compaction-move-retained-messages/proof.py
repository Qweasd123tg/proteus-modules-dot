#!/usr/bin/env python3
"""Offline exact stock/composed replay and focused local compaction source lift."""
import argparse
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


def check(ok,label):
    if not ok:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def ident(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest(),sha(raw)


def part(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]


def serde_free(s):
    return re.sub(r"(?m)^#\[serde\([^\n]+\)\]\n","",s).replace(", Serialize, Deserialize","")


def verify_refs(directory):
    data=json.loads(Path(__file__).with_name("SOURCE-PROVENANCE.json").read_text())
    pins=data["reproduction_inputs"]
    check({name for name in pins}=={"history","compaction","budget","tests","lock","content","ids","tool",
                                   "sdk-map","sdk-image","sdk-output","prefix","prior-517","prior-521"},
          "complete reproduction inputs")
    refs={}
    for key,p in pins.items():
        raw=(directory/(key+".ref")).read_bytes()
        check(ident(raw)==(p["git_blob"],p["sha256"]),f"identity {key}")
        refs[key]=raw
    return data,refs


def verify_git(temp,env,git,refs,patch,expected):
    files=("compaction","history","budget")
    working=temp/SOURCE
    working.mkdir(parents=True)
    originals={k:refs[k] for k in files}
    overlay={517:temp/"517.patch",521:temp/"521.patch",254:temp/"254.patch"}
    qa=env | {"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
              "GIT_CEILING_DIRECTORIES":str(temp.parent)}
    for n,b in [(517,refs["prior-517"]),(521,refs["prior-521"]),(254,patch)]:
        overlay[n].write_bytes(b)
    def get():
        return {k:(working/(k+".rs")).read_bytes() for k in files}
    def reset():
        for k,v in originals.items():
            (working/(k+".rs")).write_bytes(v)
    def step(n,reverse=False):
        flags=["-R"] if reverse else []
        for phase in (["--check"],[]):
            subprocess.run([git,"apply",*flags,*phase,overlay[n]],cwd=temp,env=qa,check=True,timeout=20)
    def against(files,state):
        for key,v in files.items():
            p=expected[state][key]
            check(ident(v)==(p["git_blob"],p["sha256"]),f"{state}:{key}")
    reset()
    step(254)
    candidate=get()
    against(candidate,"standalone")
    step(254,True)
    check(get()==originals,"standalone reversal")
    step(517)
    step(521)
    before=get()
    against(before,"prior_both")
    step(521,True)
    step(517,True)
    check(get()==originals,"prior reversal")
    common=None
    for order in permutations(overlay):
        states=[get()]
        for n in order:
            step(n)
            states.append(get())
        result=states.pop()
        against(result,"combined")
        if common is None:
            common=result
        else:
            check(common==result,"byte-identical composition")
        for n in reversed(order):
            step(n,True)
            check(get()==states.pop(),"exact per-step rollback")
    return dict(stock=originals,candidate=candidate,prior=before,composed=common)


def exact_output(r):
    s=r["sdk-output"]
    dto=part(s,"pub struct ContextPreparationOutput {","/// Diagnostics for an unchanged")
    ctor=part(s,"    pub fn changed(messages: Vec<CanonicalMessage>","    pub fn unchanged(messages:")
    return "#[derive(Debug,Clone,PartialEq)]\n"+dto+"\nimpl ContextPreparationOutput {\n"+ctor+"}\n"


def variant(name,files,tests):
    h=files["history"].decode()
    b=files["budget"].decode()
    c=files["compaction"].decode()
    history=part(h,"pub(crate) struct HistoryParts")
    if "use std::borrow::Cow;" in h:
        history="use std::borrow::Cow;\n"+history
    history="use crate::domain::new_message_id;\n"+history
    history=history.replace("crate::budget::estimate_text_tokens","estimate_text_tokens")
    budget=part(b,"const DEFAULT_USER_MESSAGE_BUDGET_TOKENS","/// Mirrors the pinned Codex")
    budget+=part(b,"pub(crate) fn user_message_budget_tokens(")
    tail=part(c,"    let user_messages = collect_user_messages","\nfn unchanged_without_trigger")
    check(tail.count("complete_summary_with_recovery(&input, config, history.summary_history, host)?;")==1,
          "unchanged exact error/call boundary")
    call=part(tail,"    let replacement = replacement_messages(","    let output_token_estimate")
    measure_call=call.replace("&history.ephemeral_context","ephemeral").replace("&summary","summary")
    existing=(part(tests,"#[test]\nfn compacted_image_users_match_upstream_text_only_reconstruction","\nuse crate::{\n    budget::")
              +part(tests,"#[test]\nfn retained_user_history_is_newest_first_budgeted_then_restored_in_order",
                    "#[test]\nfn no_summary_budget"))
    existing=existing.replace("    use proteus_contracts::domain::ImageRef;\n","").replace("crate::history::","")
    return (f"mod {name} {{\nuse super::*;\n"+history+budget+
            "pub(super) fn local(rows:&[CanonicalMessage],host:&mut Host)->Result<ContextPreparationOutput,Failure>{\n"
            "    let history=split_history(rows);\n    assert!(!history.compactable_history.is_empty());\n    let input=();\n    let config=&();\n"
            "    let token_estimate=41u32;\n    let trigger_tokens=7u32;\n"+tail+
            "pub(super) fn measure(rows:&[CanonicalMessage],ephemeral:&[CanonicalMessage],summary:&str)->Metered {\n"
            "    let preserved_user_messages=select_recent_user_messages(rows,user_message_budget_tokens());\n"
            "    assert_eq!(preserved_user_messages.messages.len(),1);\n"
            "    let before=text_ptr(&preserved_user_messages.messages[0]);\n"
            "    assert!(METER.replace(Some(Stats::default())).is_none());\n"+measure_call+
            "    let counters=METER.take().unwrap();\n"
            "    let after=text_ptr(&replacement[1]);\n"
            "    Metered{rows:replacement,stats:counters,same_payload:before==after}\n}\n"
            +existing+"}\n")


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

MACRO=r'''
use serde_json::Value;
macro_rules! json {
    ({$($key:literal: $value:expr),+ $(,)?}) => {
        Value::Object(BTreeMap::from([$(($key.into(),Value::Number($value as i64))),+]))
    };
}
'''

TESTS=r'''
#[derive(Debug,Clone,PartialEq,Eq)]
enum Failure { Transport(&'static str), Cancelled }
struct Host {
    summary:Result<String,Failure>,
    seen:Vec<Vec<(MessageId,Vec<PartId>)>>,
}
fn complete_summary_with_recovery(_: &(),_: &(),messages:Vec<CanonicalMessage>,host:&mut Host)
    ->Result<String,Failure> {
    host.seen.push(messages.iter().map(|m|(m.id,m.parts.iter().map(|p|p.part_id).collect())).collect());
    host.summary.clone()
}
type Run=fn(&[CanonicalMessage],&mut Host)->Result<ContextPreparationOutput,Failure>;
const ARMS:[Run;4]=[stock::local,candidate::local,prior::local,composed::local];
fn init_ids() { MESSAGE.set(1_000_000); PART.set(2_000_000); }
fn compared(rows:&[CanonicalMessage],summary:Result<String,Failure>)->(Result<ContextPreparationOutput,Failure>,usize) {
    let one=|f:Run| {
        init_ids();
        let mut host=Host{summary:summary.clone(),seen:vec![]};
        let output=f(rows,&mut host);
        (output,host.seen,MESSAGE.get(),PART.get())
    };
    let s=one(ARMS[0]);
    for a in &ARMS[1..] { assert_eq!(one(*a),s); }
    assert_eq!(s.1.len(),1);
    let want=rows.iter().map(|m|(m.id,m.parts.iter().map(|p|p.part_id).collect::<Vec<_>>())).collect::<Vec<_>>();
    assert_eq!(s.1[0],want);
    (s.0,(s.2-1_000_000) as usize)
}
fn msg(role:MessageRole,text:&str)->CanonicalMessage { CanonicalMessage::text(role,text) }
fn ctx(text:&str)->CanonicalMessage {
    let mut m=msg(MessageRole::Developer,text);
    m.parts[0].scope=PartScope::Request;
    m
}
fn image()->CanonicalMessage {
    let mut m=CanonicalMessage::new(MessageRole::User,vec![ContentPart::Image {
        image: ImageRef{id:"fixture".into(),name:"image.png".into(),mime_type:"image/png".into(),
                        path:"inert".into()}
    }]);
    m.phase=Some(MessagePhase::FinalAnswer);
    m.name=Some("全 envelope 🧪".into());m.tool_call_id=Some("id:7".into());
    m.metadata=Value::Object(BTreeMap::from([("keep".into(),Value::Array(vec![Value::Bool(true),Value::Number(7)]))]));
    m
}
fn summary(out:&ContextPreparationOutput,s:&str) {
    let last=out.messages.last().unwrap();
    assert_eq!(last.role,MessageRole::User);assert_eq!(last.metadata,Value::Null);
    assert_eq!(last.parts.len(),1);
    let p=&last.parts[0];
    assert_eq!((p.provenance,p.scope),(PartProvenance::Compactor,PartScope::Conversation));
    assert_eq!(p.payload,ContentPart::Text{text:s.into()});
}

#[test]
fn real_local_tail_preserves_empty_one_and_multiple_order_counts_and_ephemeral() {
    let context=ctx("injected");
    let a=msg(MessageRole::User,"first");
    let b=msg(MessageRole::User,"latest");
    let s=format!("{SUMMARY_PREFIX}\nretained summary");
    for (rows,ordered,kept,diagnostics) in [
        (vec![context.clone(),msg(MessageRole::Assistant,"durable")],vec![context.clone()],0,1),
        (vec![context.clone(),a.clone()],vec![context.clone(),a.clone()],1,1),
        (vec![context.clone(),a.clone(),b.clone()],vec![a.clone(),context.clone(),b.clone()],2,2),
        (vec![a.clone(),b.clone()],vec![a.clone(),b.clone()],2,2),
    ]{
        let retained_context=usize::from(rows.iter().any(|p|p.id==context.id));
        let (out,ids)=compared(&rows,Ok(s.clone()));
        let out=out.unwrap();
        assert_eq!(ids,1);
        assert_eq!(&out.messages[..out.messages.len()-1],ordered.as_slice());
        assert_eq!(out.metadata,json!({"compacted_messages":diagnostics,"preserved_user_messages":kept,
                                       "ephemeral_context_messages":retained_context}));
        assert_eq!(out.summary.as_deref(),Some(s.as_str()));
        assert_eq!(out.original_token_estimate,Some(41));assert_eq!(out.trigger_tokens,Some(7));
        assert_eq!(out.summary_source.as_deref(),Some("model"));
        assert!(out.changed);assert!(out.skipped_reason.is_none());
        assert!(out.user_message_replacements.is_empty());
        summary(&out,&s);
    }
}
#[test]
fn local_partial_and_image_only_map_preserve_owned_envelope() {
    let source=image();
    let (out,ids)=compared(&[source.clone()],Ok("summary".into()));
    assert_eq!(ids,2);
    let out=out.unwrap();
    let first=&out.messages[0];
    assert_eq!(out.user_message_replacements,vec![CompactionUserMessageReplacement{
        source_message_id:source.id,replacement_message_id:first.id
    }]);
    assert_ne!(first.id,source.id);
    assert_eq!((&first.role,first.phase,&first.name,&first.tool_call_id,&first.metadata),
               (&source.role,source.phase,&source.name,&source.tool_call_id,&source.metadata));
    assert_eq!(first.parts[0].payload,ContentPart::Text{text:String::new()});
    let source=msg(MessageRole::User,&"界".repeat(27_000));
    let (out,ids)=compared(&[source.clone()],Ok("summary".into()));
    let out=out.unwrap();
    assert_eq!(ids,2);
    assert_eq!(out.user_message_replacements[0].source_message_id,source.id);
    assert_eq!(out.user_message_replacements[0].replacement_message_id,out.messages[0].id);
    assert!(out.messages[0].display_text().contains("tokens truncated"));
    summary(&out,"summary");
}
#[test]
fn failed_or_cancelled_summary_keeps_preselection_but_emits_no_output_or_summary_id() {
    for failure in [Failure::Transport("exact fixture error"),Failure::Cancelled] {
        let ordinary=[ctx("context"),msg(MessageRole::User,"kept")];
        let (out,ids)=compared(&ordinary,Err(failure.clone()));
        assert_eq!((out,ids),(Err(failure.clone()),0));
        let image_boundary=[ctx("context"),image()];
        let (out,ids)=compared(&image_boundary,Err(failure.clone()));
        assert_eq!((out,ids),(Err(failure),1)); // image preselection ID only
    }
}
#[test]
fn generated_full_outputs_four_way_with_inert_same_paths() {
    let mut rng=41u64;
    let mut next=|n:usize|{rng=rng.wrapping_mul(6364136223846793005).wrapping_add(1);(rng>>33)as usize%n};
    for i in 0..4096 {
        let mut rows=vec![msg(MessageRole::Assistant,"durable fixture")];
        for _ in 0..next(10) {
            rows.push(match next(9) {
                0=>ctx("context"),1=>image(),2=>msg(MessageRole::User,""),
                3=>msg(MessageRole::User,"actual reply"),
                4=>msg(MessageRole::User,"<turn_aborted> ignored"),
                5=>msg(MessageRole::Assistant,"reasoning"),
                6=>msg(MessageRole::User,&format!("{SUMMARY_PREFIX}\nprior summary")),
                7=>msg(MessageRole::User,"壱二三"),
                _=>msg(MessageRole::Tool,"fixture output"),
            });
        }
        let result=if i%11==0 {Err(Failure::Cancelled)} else {Ok(format!("tag {i} 样"))};
        let _=compared(&rows,result);
    }
}

#[derive(Clone,Copy,Debug,Default)]
struct Stats {alloc:usize,realloc:usize,bytes:usize}
struct Metered {rows:Vec<CanonicalMessage>,stats:Stats,same_payload:bool}
thread_local!{static METER:Cell<Option<Stats>>=const{Cell::new(None)};}
fn request(bytes:usize,reallocation:bool) {
    let _=METER.try_with(|m|if let Some(mut s)=m.get(){
        if reallocation{s.realloc+=1;}else{s.alloc+=1;}s.bytes+=bytes;m.set(Some(s));
    });
}
struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {request(n,true);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout) {unsafe{System.dealloc(p,l)}}
}
#[global_allocator] static ALLOCATOR:Meter=Meter;
fn text_ptr(m:&CanonicalMessage)->usize {
    let ContentPart::Text{text}=&m.parts[0].payload else {unreachable!()};
    assert!(!text.is_empty());
    text.as_ptr() as usize
}
#[test]
fn seventy_two_kib_at_real_budget_allocations_and_selected_payload_identity() {
    let bytes=72*1024;
    let rows=[msg(MessageRole::User,&"r".repeat(bytes))];
    let ephemeral=[ctx("inert scope")];
    type Measure=fn(&[CanonicalMessage],&[CanonicalMessage],&str)->Metered;
    for (tag,left,right) in [
        ("stock",stock::measure as Measure,candidate::measure as Measure),
        ("composed",prior::measure as Measure,composed::measure as Measure),
    ] {
        init_ids();let a=left(black_box(&rows),&ephemeral,"summary");
        init_ids();let b=right(black_box(&rows),&ephemeral,"summary");
        assert_eq!(a.rows,b.rows);
        assert_eq!(b.rows[1],rows[0]);
        assert_eq!(b.rows[0],ephemeral[0]);
        assert!(!a.same_payload);assert!(b.same_payload);
        assert!(a.stats.alloc>b.stats.alloc);
        assert!(a.stats.bytes-b.stats.bytes>=bytes);
        let (x,y)=(a.stats,b.stats);
        println!("R254_ALLOC {tag} {} {} {} {} {} {}",x.alloc,x.realloc,x.bytes,y.alloc,y.realloc,y.bytes);
    }
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("refs","work","rustc"):
        p.add_argument("--"+k,type=Path,required=True)
    p.add_argument("--git",type=Path,default=Path("/usr/bin/git"))
    args=p.parse_args()
    git=args.git.resolve(strict=True);rustc=args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC_SHA,"compiler identity")
    meta,raw=verify_refs(args.refs)
    lock=next(b for b in raw["lock"].decode().split("[[package]]") if '\nname = "proteus-contracts"\n' in b)
    check(f"?rev={CORE}#{CORE}" in lock,"locked SDK")
    patch=Path(__file__).with_name("source.patch").read_bytes()
    check(ident(patch)==(meta["source_patch"]["git_blob"],meta["source_patch"]["sha256"]),"exact patch")
    with tempfile.TemporaryDirectory(prefix="r254-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        arms=verify_git(root,env,git,raw,patch,meta["identities"])
        refs={k:v.decode() for k,v in raw.items()}
        code=STUB+MACRO+contract(refs)+exact_output(refs)+"\nconst SUMMARY_PREFIX:&str="+json.dumps(refs["prefix"],ensure_ascii=False)+";\n"
        code+="".join(variant(k,v,refs["tests"]) for k,v in arms.items())+TESTS
        unit=root/"lift.rs";unit.write_text(code,encoding="utf-8")
        results={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,"-o",exe],
                           check=True,cwd=root,env=env,timeout=90)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               capture_output=True,text=True,timeout=90)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 17 passed; 0 failed;" in out.stdout,"test count")
            measures={}
            for k,v in re.findall(r"(?m)\bR254_ALLOC (\w+) ((?:\d+ ){5}\d+)$",out.stdout):
                n=list(map(int,v.split()))
                measures[k]=dict(stock_alloc_realloc_requested_bytes=n[:3],candidate_alloc_realloc_requested_bytes=n[3:])
            check(set(measures)=={"stock","composed"},"allocator scope receipts")
            results[mode]=dict(tests_passed=17,generated_four_arm_cases=4096,allocations=measures)
    print(json.dumps(dict(status="PASS",rustc=version,rustc_sha256=RUSTC_SHA,
                          locked_sdk=CORE,exact_raw_permutations_and_reverses=6,results=results),indent=2))


if __name__=="__main__":
    main()
