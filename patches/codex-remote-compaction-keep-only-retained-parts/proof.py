#!/usr/bin/env python3
"""Verify exact remote-history reconstruction; no provider or database."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

PATH="hook/codex-context-preparation/src/remote_history.rs"
CORE="0c1b7572313230e5d123e95c722e1258a2e9ecd6"
RUSTC_SHA="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION="rustc 1.95.0 (59807616e 2026-04-14)"
PINS={
    "stock": ("1eafe83a51b5106471bf0ae8a463cfa52e870fa1","98b3f9fdbb7ea48b3e144d443314f405e89880d95ce6c01e5f6967f6cad59513"),
    "candidate": ("1a0a79f3f4a68aeb31857f1b63b2463af790ede4","4f40fc217f9286c6349ff48b466663acccd7c725bcfe2483563e5004007af901"),
    "patch": ("b2ca868f46bd84abdec542f34aa494f656860061","13ea3c288156534a87ab39046f94588ca1832df236498a372f0d802cec0607f3"),
    "lock": ("ae7035fc5900b0afc480e55d2408c8234c88dd17","0b4717cd37ba4b5848068f64c52e863000d8d7ea6d90464f4a134689e45bef54"),
    "testremote": ("f167f4d0c7c2a80f1964a005cbb1ac6769ac89dd","be70f83229a0c5174f6aabda8a21b57779d884f4cc9f086b40ea47ecc92c5afb"),
    "remote": ("522c81ee994f5a222b18de54438ca1d0afd53f22","44ed93cd0382a84d9a951804d19e2e84e3939dbeb94be423f2c248e6e1f1973e"),
    "budget": ("a8d9f214706e9b56b6467f0ea8c8d52222744a40","ec5cb864eb0e8219e252b435c2718163020ccfe063f68aec87dce159534e8e14"),
    "history": ("b08a08f16cda6b4a96e3c813d0c810e378473d1a","a778193e1d6c9cd25f0e6875a1a9fde78b8cab5adec967f95d8a667c1400ebb1"),
    "content": ("9675ad69faa4e300aa5a00d8128f6992eeff4c57","fe74614f707d36f73a63028af19ecfed2abc6cf2619080607f39d35f9aa974c0"),
    "ids": ("5ba1255896286e32754b87e25c91127d1faf42c7","4b8c20657e1690a6f34891ab3f0b9081bef9b1781b6e784cecb7833c5ef4f07f"),
    "tool": ("a4fb43299a3168511595ff7112e71b787cb2d23d","94de0b99e3e161776eb0829dc9b83207d55afab0709d90de5fa968bcdd9e0e7c"),
    "sdk-map": ("45e806cf231b03bf8fe782b7e5a5362b0dfcca8c","658b9b8067592dae6ffb49ad538e9bd22e2ccac360068c872103bcace6b79cb0"),
    "sdk-image": ("a007ba1a28ac13fa6522c1bf74c84b4906d4a66e","bb8870ec40dfaf77418b88823033be1fe67f334f35a5e82bbd884e9ea4e09c7f"),
}


def check(ok,label):
    if not ok:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def identity(b):
    return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest(),sha(b)


def replay(raw,patch,reverse=False):
    h=(f"diff --git a/{PATH} b/{PATH}\n"
       f"index {PINS['stock'][0]}..{PINS['candidate'][0]} 100644\n"
       f"--- a/{PATH}\n+++ b/{PATH}\n").encode()
    check(patch.startswith(h),"one exact source file")
    tokens=re.split(rb"(?m)(^@@ [^\n]+\n)",patch[len(h):])
    check(len(tokens)==5 and tokens[0]==b"","two hunks")
    out=[];line=0;source=raw.splitlines(keepends=True)
    for label,body in zip(tokens[1::2],tokens[2::2]):
        m=re.fullmatch(rb"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n",label)
        check(m is not None,"exact hunk")
        a,n,b,k=map(int,m.groups())
        rows=body.splitlines(keepends=True)
        check(all(r[:1] in (b" ",b"-",b"+") for r in rows),"hunk lines")
        old,new=([r[1:] for r in rows if r[:1]!=skip] for skip in (b"+",b"-"))
        check((len(old),len(new))==(n,k),"hunk sizes")
        if reverse:
            a,b=b,a
            old,new=new,old
        check(line<=a-1 and source[a-1:a-1+len(old)]==old,"hunk exact preimage")
        out.extend(source[line:a-1])
        check(len(out)==b-1,"hunk exact postimage offset")
        out.extend(new)
        line=a-1+len(old)
    return b"".join(out+source[line:])


def part(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]


def serde_free(s):
    return re.sub(r"(?m)^#\[serde\([^\n]+\)\]\n","",s).replace(", Serialize, Deserialize","")


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


def lifted(tag,raw,r):
    s=raw.decode()
    test=r["testremote"]
    source=part(s,"const AUTO_IMAGE_TOKENS","pub(crate) fn estimate_messages(")+part(s,"fn message_tokens(")
    internal=(
        part(test,"    let old = CanonicalMessage::text(MessageRole::User, \"old\");",
             "\n}\n\n#[test]\nfn remote_boundary_keeps")
        + "\n}\n"
    )
    image_helper=part(test,"fn image(id: &str)","#[test]")
    emitted_tests=(
        image_helper + "#[test]\nfn remote_image_boundary_retains_later_parts_atomically_and_does_not_backfill() {\n"
        +internal
        +part(test,"#[test]\nfn fitting_image_labels_stay_together_in_a_truncated_boundary_message(",
              "#[test]\nfn remote_output_estimate_charges")
    ).replace("crate::remote_history::select_recent_users","select_recent_users")
    id_import="use crate::domain::new_message_id;\n" if "ToolContent, new_message_id" in s else ""
    return f"#[allow(unreachable_patterns)]\nmod {tag} {{\nuse super::*;\n"+id_import+source+emitted_tests+"}\n"


def support(r):
    h=r["history"];b=r["budget"]
    return (part(b,"pub(crate) fn estimate_text_tokens(","/// Mirrors the pinned Codex")
            +"#[derive(Debug,PartialEq)]\n"
            +part(h,"#[derive(Default)]\npub(crate) struct SelectedUserMessages","pub(crate) fn select_recent_user_messages")
            +part(h,"pub(crate) fn part_text("))


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

TESTS=r'''
use serde_json::Value;
type Selector=fn(&[CanonicalMessage],usize)->SelectedUserMessages;
fn text(text:&str)->ContentPart {ContentPart::Text{text:text.into()}}
fn image(id:&str)->ContentPart {
    ContentPart::Image{image:ImageRef{id:id.into(),name:"fixture".into(),mime_type:"image/png".into(),
                                     path:"inert".into()}}
}
fn envelope(role:MessageRole, payloads:Vec<ContentPart>)->CanonicalMessage {
    let mut m=CanonicalMessage::new(role,payloads);
    m.phase=Some(MessagePhase::FinalAnswer);
    m.name=Some("全 envelope 🧪".into());
    m.tool_call_id=Some("epoch:案:0005".into());
    m.metadata=Value::Object(BTreeMap::from([
        ("marker".into(), Value::String("durable🔒".into())),
        ("nested".into(), Value::Array(vec![Value::Null,Value::Bool(false),Value::Number(-22)]))
    ]));
    m
}
fn seeded(f:Selector,rows:&[CanonicalMessage],limit:usize)->(SelectedUserMessages,u128,u128) {
    MESSAGE.set(900_000);
    PART.set(1_900_000);
    let out=f(rows,limit);
    (out,MESSAGE.get()-900_000,PART.get()-1_900_000)
}
fn paired(rows:&[CanonicalMessage],limit:usize)->(SelectedUserMessages,u128,u128) {
    let x=seeded(stock::select_recent_users,rows,limit);
    let y=seeded(candidate::select_recent_users,rows,limit);
    assert_eq!(x,y);
    y
}

#[test]
fn exact_nondefault_envelope_multiple_parts_and_replacement_identity() {
    let older=envelope(MessageRole::User,vec![text("older")]);
    let mut boundary=envelope(MessageRole::User,vec![text("keep"),text(&"界".repeat(100)),text("drop tail")]);
    boundary.parts[0].scope=PartScope::Request;
    boundary.parts[1].scope=PartScope::Trace;
    boundary.parts[2].scope=PartScope::Conversation;
    let newest=envelope(MessageRole::User,vec![text("new")]);
    let rows=[older,boundary.clone(),newest.clone()];
    let seed=rows.clone();
    let (out, fresh_messages, fresh_parts)=paired(&rows,5);
    assert_eq!(rows,seed);
    assert_eq!((fresh_messages,fresh_parts),(1,2));
    assert_eq!(out.messages.len(),2);
    assert_eq!(out.messages[1],newest);
    let m=&out.messages[0];
    assert_eq!(m.id,900_000);
    assert_ne!(m.id,boundary.id);
    assert_eq!(m.role,boundary.role);
    assert_eq!(m.phase,boundary.phase);
    assert_eq!(m.name,boundary.name);
    assert_eq!(m.tool_call_id,boundary.tool_call_id);
    assert_eq!(m.metadata,boundary.metadata);
    assert_eq!(m.parts.len(),2);
    assert_eq!(m.parts[0].payload,text("keep"));
    let expected=truncate_to_tokens(&"界".repeat(100),3);
    assert_eq!(m.parts[1].payload,text(&expected));
    for (i,p) in m.parts.iter().enumerate() {
        assert_eq!(p.part_id,1_900_000+i as u128);
        assert_ne!(p.part_id,boundary.parts[i].part_id);
        assert_eq!((p.provenance,p.scope),(PartProvenance::Compactor,PartScope::Conversation));
    }
    assert_eq!(out.replacements,vec![CompactionUserMessageReplacement {
        source_message_id:boundary.id,replacement_message_id:m.id }]);
}

#[test]
fn zero_exact_fit_and_whole_order_keep_existing_identity() {
    let rows=[envelope(MessageRole::User,vec![]),envelope(MessageRole::User,vec![text("fit")])];
    let (none,m,p)=paired(&rows,0);
    assert!(none.messages.is_empty() && none.replacements.is_empty());
    assert_eq!((m,p),(0,0));
    let (whole,m,p)=paired(&rows,2);
    assert_eq!(whole.messages,rows);
    assert_eq!((m,p),(0,0));
    assert!(whole.replacements.is_empty());
    let (last,m,p)=paired(&rows,1);
    assert_eq!(last.messages,rows[1..]);
    assert_eq!((m,p),(0,0));
}
#[test]
fn no_fit_boundary_consumes_budget_without_backfill() {
    let rows=[envelope(MessageRole::User,vec![text("older")]),envelope(MessageRole::User,vec![image("huge")])];
    let (no_fit,m,p)=paired(&rows,1);
    assert_eq!((m,p),(0,0));
    assert!(no_fit.messages.is_empty() && no_fit.replacements.is_empty());
}
#[test]
fn image_atomicity_and_current_envelope_preserved() {
    let base=envelope(MessageRole::User,vec![text(&"é".repeat(900)),text("<image>"),image("kept"),
                                             text("</image>"),text("suffix")]);
    let (out,m,p)=paired(&[base.clone()],1860);
    assert_eq!(m,1);
    assert_eq!(p,5);
    let replacement=&out.messages[0];
    assert_eq!(replacement.metadata,base.metadata);
    assert_eq!(replacement.phase,base.phase);
    assert_eq!(replacement.name,base.name);
    assert_eq!(replacement.tool_call_id,base.tool_call_id);
    assert_eq!(replacement.parts[1].payload,text("<image>"));
    assert_eq!(replacement.parts[2].payload,image("kept"));
    assert_eq!(replacement.parts[3].payload,text("</image>"));
    assert_eq!(replacement.parts[4].payload,text("suffix"));
}

#[test]
fn generated_selectors_keep_messages_maps_and_identity_counts() {
    let mut rng=0x683f_u64;
    let mut next=|n:usize| {rng=rng.wrapping_mul(6364136223846793005).wrapping_add(1);(rng>>32) as usize%n};
    for i in 0..4096 {
        let mut rows=vec![];
        for _ in 0..next(10) {
            let mut parts=vec![];
            for _ in 0..next(8) {
                parts.push(match next(7) {
                    0=>image("img"),1=>text(""),2=>text("🧪é"),
                    3=>text(&"tag ".repeat(next(80))),
                    4=>ContentPart::Reasoning{text:"ignored".into(),signature:Some("stub".into())},
                    5=>ContentPart::Opaque{format:"fixture".into(),data:Value::String("wire".into())},
                    _=>ContentPart::FileRef{path:"fixture".into(),content:Some("unchanged".into())},
                });
            }
            let row=if i%3==0 {envelope(MessageRole::User,parts)} else {CanonicalMessage::new(MessageRole::User,parts)};
            rows.push(row);
        }
        let limit=[0,1,2,7,1800,1844,1845,1870,4900,64_000,usize::MAX][next(11)];
        let (out,n,part_ids)=paired(&rows,limit);
        assert_eq!(n,out.replacements.len() as u128);
        assert!(out.replacements.len()<=1);
        if let Some(map)=out.replacements.first() {
            let selected=&out.messages[0];
            let original=rows.iter().find(|row|row.id==map.source_message_id).unwrap();
            assert_eq!(selected.id,map.replacement_message_id);
            assert_eq!((&selected.role,selected.phase,&selected.name,&selected.tool_call_id,&selected.metadata),
                       (&original.role,original.phase,&original.name,&original.tool_call_id,&original.metadata));
            assert_eq!(part_ids,selected.parts.len() as u128);
        } else {assert_eq!(part_ids,0)}
    }
}

#[derive(Clone,Copy,Debug,Default)]
struct Stats {alloc:usize,realloc:usize,bytes:usize}
thread_local! {static METER:Cell<Option<Stats>>=const {Cell::new(None)};}
fn request(n:usize,reallocation:bool) {
    let _=METER.try_with(|m| if let Some(mut s)=m.get(){
        if reallocation {s.realloc+=1;} else {s.alloc+=1;} s.bytes+=n; m.set(Some(s));
    });
}
struct Meter;
unsafe impl GlobalAlloc for Meter {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {request(n,true);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout) {unsafe{System.dealloc(p,l)}}
}
#[global_allocator]
static ALLOCATOR:Meter=Meter;
fn measured(f:Selector,rows:&[CanonicalMessage],limit:usize)->(SelectedUserMessages,Stats) {
    MESSAGE.set(900_000);PART.set(1_900_000);
    assert!(METER.replace(Some(Stats::default())).is_none());
    let selected=black_box(f)(black_box(rows),limit);
    (selected,METER.take().unwrap())
}

#[test]
fn partial_64k_case_scoped_requests_exclude_fixture_setup() {
    let payload=2*1024*1024;
    let dropped=1024*1024;
    let mut large=envelope(MessageRole::User,vec![
        ContentPart::Text{text:"a".repeat(payload)},
        ContentPart::Reasoning{text:"b".repeat(dropped),signature:None},
    ]);
    large.metadata=Value::Object(BTreeMap::from([("must retain".into(),
        Value::Array(vec![Value::String("metadata".repeat(1024)),Value::Bool(true)]))]));
    let rows=[large,CanonicalMessage::text(MessageRole::User,"latest")];
    let (a,x)=measured(stock::select_recent_users,&rows,64_000);
    let (b,y)=measured(candidate::select_recent_users,&rows,64_000);
    assert_eq!(a,b);
    assert_eq!(b.messages.len(),2);
    assert_eq!(b.replacements.len(),1);
    assert_eq!(b.messages[0].metadata,rows[0].metadata);
    assert_eq!(b.messages[0].parts.len(),1);
    assert_eq!(x.alloc-y.alloc,3);
    assert_eq!(x.realloc,y.realloc);
    assert_eq!(x.bytes-y.bytes,payload+dropped+2*std::mem::size_of::<CanonicalPart>());
    println!("R253_ALLOC {} {} {} {} {} {}",x.alloc,x.realloc,x.bytes,y.alloc,y.realloc,y.bytes);
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("refs","rustc","work"):
        p.add_argument("--"+k,type=Path,required=True)
    args=p.parse_args()
    refs={}
    for k,pin in PINS.items():
        if k in ("patch","candidate"):
            continue
        b=(args.refs/(k+".ref")).read_bytes()
        check(identity(b)==pin,"identity: "+k)
        refs[k]=b.decode()
    lock=next(p for p in refs["lock"].split("[[package]]") if '\nname = "proteus-contracts"\n' in p)
    check(f"?rev={CORE}#{CORE}" in lock,"locked Core SDK")
    check("let retained = select_recent_users(&users, 64_000);" in refs["remote"],"production budget")
    patch=Path(__file__).with_name("source.patch").read_bytes()
    check(identity(patch)==PINS["patch"],"patch pin")
    stock=refs["stock"].encode()
    candidate=replay(stock,patch)
    check(identity(candidate)==PINS["candidate"] and replay(candidate,patch,True)==stock,"patch round trip")
    expect=candidate.replace(b"    domain::{CompactionUserMessageReplacement, ToolContent},",
                             b"    domain::{CompactionUserMessageReplacement, ToolContent, new_message_id},")
    observed=part(candidate.decode(),"        let mut replacement = CanonicalMessage::from_parts(","        selected")
    expect=expect.replace(observed.encode(),b"        let mut replacement = message.clone();\n"
                          b"        replacement.id = new_message_id();\n        replacement.parts = parts;\n")
    check(expect==stock,"no changed callsite or other path")
    rustc=args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC_SHA,"compiler pin")
    with tempfile.TemporaryDirectory(prefix="r253-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        unit=root/"lift.rs"
        unit.write_text(STUB+contract(refs)+support(refs)+lifted("stock",stock,refs)+lifted("candidate",candidate,refs)+TESTS,
                        encoding="utf-8")
        results={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,"-o",exe],
                           check=True,cwd=root,env=env,timeout=90)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,text=True,
                               capture_output=True,timeout=90)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 10 passed; 0 failed;" in out.stdout,"test count")
            m=re.search(r"(?m)\bR253_ALLOC ((?:\d+ ){5}\d+)$",out.stdout)
            check(m is not None,"allocation receipt")
            n=list(map(int,m[1].split()))
            results[mode]={"tests_passed":10,"generated_full_result_pairs":4096,
                           "stock_alloc_realloc_requested_bytes":n[:3],
                           "candidate_alloc_realloc_requested_bytes":n[3:]}
    print(json.dumps(dict(status="PASS",rustc=version,rustc_sha256=RUSTC_SHA,locked_core=CORE,
                          exact_patch_roundtrip=True,results=results,actual_provider_or_serde_run=False),indent=2))


if __name__=="__main__":
    main()
