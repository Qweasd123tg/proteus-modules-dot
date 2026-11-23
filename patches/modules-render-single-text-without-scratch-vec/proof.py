#!/usr/bin/env python3
"""Replay and verify the exact single-text output projection with no fallback edits."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "workflow/coding-workflow/src/output_text.rs"
BASE_BLOB = "73f1dd474a2617b9f2aae82439ce78c5118c65bf"
BASE_SHA = "aa9c782251c6b53fffe4e47512427f6ff7e7a769bcf9dd93c90ad9c01e0648c9"
AFTER_BLOB = "b8fee51523911684fba1ecd672541efaf50ccebc"
AFTER_SHA = "fd78180b9956965345951857af37a1c8c6075048868fa1b7a903dc87fde40730"
PATCH_SHA = "b5e45d328ae4c66989196c21420c6cdffa1ae5e0ab9a3982b56014bbc5c5e7de"


def check(condition, label):
    if not condition:
        raise ValueError(label)


def identity(source, blob, digest):
    check(hashlib.sha256(source).hexdigest() == digest, "SHA256")
    git_bytes = b"blob " + str(len(source)).encode() + b"\0" + source
    check(hashlib.sha1(git_bytes).hexdigest() == blob, "Git blob")


def replay(src, patch, reverse=False):
    lines = src.splitlines(keepends=True)
    expected_header = (
        f"diff --git a/{PATH} b/{PATH}\n"
        f"index {BASE_BLOB}..{AFTER_BLOB} 100644\n"
        f"--- a/{PATH}\n+++ b/{PATH}\n"
    ).encode()
    check(patch.startswith(expected_header), "patch header")
    hunks = patch[len(expected_header):].splitlines(keepends=True)
    used = 0
    target = []
    index = 0
    count = 0
    while index < len(hunks):
        match = re.fullmatch(rb"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n", hunks[index])
        check(match is not None, "patch hunk")
        before, before_count, after, after_count = map(int, match.groups())
        index += 1
        count += 1
        before_lines, after_lines = [], []
        while index < len(hunks) and not hunks[index].startswith(b"@@ "):
            line = hunks[index]
            check(line[:1] in (b" ", b"+", b"-"), "patch hunk body")
            if line[:1] != b"+":
                before_lines.append(line[1:])
            if line[:1] != b"-":
                after_lines.append(line[1:])
            index += 1
        check((len(before_lines), len(after_lines)) == (before_count, after_count),
              "patch counts")
        if reverse:
            before, after = after, before
            before_lines, after_lines = after_lines, before_lines
        at = before - 1
        check(used <= at and lines[at:at + len(before_lines)] == before_lines, "patch preimage")
        target.extend(lines[used:at])
        check(len(target) == after - 1, "patch coordinates")
        target.extend(after_lines)
        used = at + len(before_lines)
    check(count == 1, "expected one message_text hunk")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
LOCKED_CORE = "0c1b7572313230e5d123e95c722e1258a2e9ecd6"
REFS = {
    "content": ("9675ad69faa4e300aa5a00d8128f6992eeff4c57",
                "fe74614f707d36f73a63028af19ecfed2abc6cf2619080607f39d35f9aa974c0"),
    "tool": ("a4fb43299a3168511595ff7112e71b787cb2d23d",
             "94de0b99e3e161776eb0829dc9b83207d55afab0709d90de5fa968bcdd9e0e7c"),
    "lock": ("ae7035fc5900b0afc480e55d2408c8234c88dd17",
             "0b4717cd37ba4b5848068f64c52e863000d8d7ea6d90464f4a134689e45bef54"),
    "helpers": ("c0a35a50c1a42f759d6930a530dc9e9e9fba0977",
                "ef4ce9f324565d91dcf5a99575dfbc514f41bfb9ca73b6229a471c59adb61e1b"),
}


def prior_tests(source):
    start = "#[test]\nfn empty_text_response_gets_placeholder()"
    omit = "#[test]\nfn estimates_tokens_from_text_context_and_tool_results()"
    after = "#[test]\nfn empty_final_output_truncates_tool_summary_at_unicode_scalar_boundary()"
    body = section(source, start, omit) + source[source.index(after):]
    check(body.count("#[test]") == 5 and "estimate_message_tokens" not in body,
          "five prior fallback/response fixtures")
    return body


def lift(name, full_source, tests):
    return f"mod {name} {{\n" + full_source + "\nmod adopted {\nuse super::*;\nuse crate::MessageRole;\n" + tests + "\n}\n}\n"


def dto_refs(refs):
    lock = re.search(r'\[\[package\]\]\nname = "proteus-contracts"\n[^\[]+', refs["lock"])
    check(lock is not None and f"?rev={LOCKED_CORE}#{LOCKED_CORE}" in lock[0], "exact SDK lock")
    content = refs["content"]
    for start, expected in [
        ("pub struct CanonicalMessage {", "    pub parts: Vec<CanonicalPart>,"),
        ("pub struct CanonicalPart {", "    pub payload: ContentPart,"),
    ]:
        check(expected in section(content, start, "\n}"), "actual canonical ownership")
    for expected in ["    Text {\n        text: String,", "    ToolResult {\n        result: ToolResult,"]:
        check(expected in section(content, "pub enum ContentPart {", "\n}"), "actual part fields")
    tool = section(refs["tool"], "pub struct ToolResult {", "\n}")
    check("pub output: String," in tool and "pub error: Option<String>," in tool,
          "actual fallback fields")


TESTS = r'''
extern crate self as proteus_contracts;
use std::{alloc::{GlobalAlloc,Layout,System},cell::Cell,hint::black_box};

pub mod domain {
    pub use crate::ToolResult;
    pub fn new_call_id() -> String { "synthetic-call".into() }
}
pub mod model_standard { pub use crate::{CanonicalMessage,ContentPart}; }
macro_rules! json { ({}) => { () }; }

#[derive(Clone)]
pub struct ToolResult { output:String,error:Option<String> }
impl ToolResult {
    fn new(_:String,_:bool,output:String,_:Vec<()>,error:Option<String>,_:()) -> Self {
        Self { output,error }
    }
    fn ok(_:String,output:impl Into<String>) -> Self { Self {output:output.into(),error:None} }
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum MessageRole { Assistant, Tool, User }
#[derive(Clone)]
pub struct CanonicalMessage { role:MessageRole, parts:Vec<CanonicalPart> }
#[derive(Clone)]
pub struct CanonicalPart { payload:ContentPart }
#[derive(Clone)]
pub enum ContentPart {
    Text {text:String},
    ToolResult {result:ToolResult},
    ReasoningSummary {text:String},
    Other,
}
impl CanonicalMessage {
    fn new(role:MessageRole, parts:Vec<ContentPart>) -> Self {
        Self { role, parts:parts.into_iter().map(|payload|CanonicalPart{payload}).collect() }
    }
}
const EMPTY:&str="<empty model response>";
const FALLBACK:&str="Model returned an empty final response after the last tool call.\n\nLast tool result:\n";
fn text(s:&str)->ContentPart {ContentPart::Text{text:s.into()}}
fn reasoning(s:&str)->ContentPart {ContentPart::ReasoningSummary{text:s.into()}}
fn result(output:&str,error:Option<&str>)->ContentPart {
    ContentPart::ToolResult {result:ToolResult{output:output.into(),error:error.map(str::to_owned)}}
}
fn msg(parts:Vec<ContentPart>)->CanonicalMessage {CanonicalMessage::new(MessageRole::Assistant,parts)}
fn paired_message(message:&CanonicalMessage, byte_oracle:&str) {
    let a=stock::message_text(message);
    let b=candidate::message_text(message);
    assert_eq!(a.as_bytes(),byte_oracle.as_bytes());
    assert_eq!(a.as_bytes(),b.as_bytes());
}
fn paired_output(message:&CanonicalMessage, history:&[CanonicalMessage])->String {
    let a=stock::output_text(message,history);
    let b=candidate::output_text(message,history);
    assert_eq!(a.as_bytes(),b.as_bytes());
    b
}

#[test]
fn exact_empty_and_single_text_shapes_in_all_roles() {
    paired_message(&msg(vec![]),EMPTY);
    paired_message(&msg(vec![reasoning("not Text"),ContentPart::Other]),EMPTY);
    paired_message(&msg(vec![reasoning("ignored"),text(""),ContentPart::Other]),EMPTY);
    let histories=[CanonicalMessage::new(MessageRole::Tool,vec![result("fallback",None)])];
    for role in [MessageRole::Assistant,MessageRole::Tool,MessageRole::User] {
        for raw in [" "," \t\r\n","　","x", "á\0β\r\n🧪","e\u{301}",EMPTY] {
            let m=CanonicalMessage::new(role,vec![ContentPart::Other,text(raw),reasoning("not text")]);
            assert_eq!(m.role,role);
            paired_message(&m,raw);
            let actual=paired_output(&m,&histories);
            if raw==EMPTY {assert_eq!(actual,format!("{FALLBACK}fallback"));}
            else {assert_eq!(actual,raw);}
        }
    }
}

#[test]
fn recognized_multi_parts_preserve_all_join_separators_including_empty_fields() {
    for (parts,expected) in [
        (vec![text(""),text("")],"\n"),
        (vec![text(""),reasoning("ignore"),text("a")],"\na"),
        (vec![text(" a "),text(""),text("β\0")]," a \n\nβ\0"),
        (vec![text("A\r\n"),ContentPart::Other,text(""),text("B")],"A\r\n\n\nB"),
        (vec![text(EMPTY),text("")],"<empty model response>\n"),
    ] {
        let m=msg(parts);
        paired_message(&m,expected);
        let history=[msg(vec![result("must not surface",None)])];
        assert_eq!(paired_output(&m,&history),expected);
    }
}

#[test]
fn last_tool_result_and_literal_placeholder_fallback_remain_unmodified() {
    let empty=msg(vec![text("")]);
    let literal=msg(vec![text(EMPTY)]);
    let history=[
        CanonicalMessage::new(MessageRole::Tool,vec![result("old",Some("not selected"))]),
        CanonicalMessage::new(MessageRole::User,vec![result("before last",None),
            result("  selected\0β ",Some("\u{2003}error\n"))]),
        msg(vec![text("irrelevant latest row"),reasoning("unused")]),
    ];
    for m in [&empty,&literal] {
        assert_eq!(paired_output(m,&history),format!("{FALLBACK}selected\0β\nerror"));
    }
    let hidden=msg(vec![result("old",None),result(" \t",Some("\u{2003}"))]);
    assert_eq!(paired_output(&empty,&[hidden]),EMPTY);
    let exact="🧪".repeat(1_999);
    let history=[msg(vec![result(&exact,Some("one more"))])];
    assert_eq!(paired_output(&empty,&history),format!("{FALLBACK}{exact}\n\n[truncated]"));
}

#[test]
fn generated_mixed_message_and_history_projection() {
    let texts=[""," ","\t\n","\r","A","e\u{301}","🧪\0","界",EMPTY,"\u{2003}"];
    let mut seed=89u32;
    let mut next=|n:usize| {
        seed=seed.wrapping_mul(1664525).wrapping_add(1013904223);
        (seed>>16) as usize % n
    };
    for i in 0..4096 {
        let mut parts=Vec::new();
        let mut raw=Vec::new();
        let mut history=Vec::new();
        for _ in 0..next(18) {
            let value=texts[next(texts.len())];
            match next(5) {
                0|1=>{parts.push(text(value));raw.push(value);}
                2=>parts.push(reasoning(value)),
                3=>parts.push(result(value,None)),
                _=>parts.push(ContentPart::Other),
            }
        }
        for _ in 0..next(7) {
            let out=texts[next(texts.len())];
            let err=(next(2)==0).then(||texts[next(texts.len())]);
            history.push(msg(vec![result(out,err),text("ignore history text")]));
        }
        let m=CanonicalMessage::new(
            [MessageRole::Assistant,MessageRole::Tool,MessageRole::User][i%3],parts);
        let join=raw.join("\n");
        paired_message(&m,if join.is_empty(){EMPTY}else{&join});
        let _=paired_output(&m,&history);
    }
}

#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Stat {alloc:usize,realloc:usize,bytes:usize,events:usize,layouts:[(usize,usize,bool);32]}
thread_local! {static METER:Cell<Option<Stat>>=const {Cell::new(None)};}
fn requested(bytes:usize,alignment:usize,re:bool) {
    let _=METER.try_with(|meter| {
        if let Some(mut s)=meter.get() {
            s.bytes+=bytes;
            if re {s.realloc+=1;} else {s.alloc+=1;}
            s.layouts[s.events]=(bytes,alignment,re);
            s.events+=1;
            meter.set(Some(s));
        }
    });
}
struct Allocator;
unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self,a:Layout)->*mut u8 {requested(a.size(),a.align(),false); unsafe {System.alloc(a)}}
    unsafe fn alloc_zeroed(&self,a:Layout)->*mut u8 {requested(a.size(),a.align(),false); unsafe {System.alloc_zeroed(a)}}
    unsafe fn realloc(&self,p:*mut u8,a:Layout,n:usize)->*mut u8 {requested(n,a.align(),true); unsafe {System.realloc(p,a,n)}}
    unsafe fn dealloc(&self,p:*mut u8,a:Layout) {unsafe {System.dealloc(p,a)}}
}
#[global_allocator]
static ALLOCATOR:Allocator=Allocator;
fn measure(call:fn(&CanonicalMessage)->String,message:&CanonicalMessage)->(String,Stat) {
    assert!(METER.replace(Some(Stat::default())).is_none());
    let text=black_box(call(black_box(message)));
    let stats=METER.take().unwrap();
    (text,stats)
}

#[test]
fn one_recognized_text_removes_only_the_collector_request() {
    let input=msg(vec![reasoning("ignore"),text(&"β".repeat(4096)),ContentPart::Other]);
    let (a,before)=measure(stock::message_text,&input);
    let (b,after)=measure(candidate::message_text,&input);
    assert_eq!(a,b);
    assert_eq!(a.capacity(),b.capacity());
    assert_eq!(before.alloc,after.alloc+1);
    assert_eq!(before.realloc,after.realloc);
    assert!(before.bytes>after.bytes);
    for extra in [vec![],vec![reasoning("no Text")]] {
        let none=msg(extra);
        assert_eq!(measure(stock::message_text,&none),measure(candidate::message_text,&none));
    }
    let empty=msg(vec![text("")]);
    let (x,old)=measure(stock::message_text,&empty);
    let (y,new)=measure(candidate::message_text,&empty);
    assert_eq!(x,y);
    assert_eq!(x.capacity(),y.capacity());
    assert_eq!(old.alloc,new.alloc+1);
    println!("R247_ALLOC {} {} {} {} {} {} {} {}",
              before.alloc,before.realloc,before.bytes,after.alloc,after.realloc,after.bytes,
              a.capacity(),b.capacity());
}

#[test]
fn multi_text_requests_and_result_capacity_match_from_two_upward() {
    let mut checked=0;
    for n in 2..=128usize {
        for form in 0..3 {
            let mut parts=vec![ContentPart::Other];
            for i in 0..n {
                let content=match form {
                    0=>"β🧪\0",
                    1=>if i%3==0{" "}else{""},
                    _=>"",
                };
                parts.push(text(content));
                if i%3==1 {parts.push(reasoning("don't count"));}
                if i%5==0 {parts.push(result("ignore",None));}
            }
            let input=msg(parts);
            let (a,old)=measure(stock::message_text,&input);
            let (b,new)=measure(candidate::message_text,&input);
            assert_eq!(a.as_bytes(),b.as_bytes());
            assert_eq!(a.capacity(),b.capacity(),"n={n}, form={form}");
            assert_eq!(old,new,"request sequence n={n}, form={form}");
            checked+=1;
        }
    }
    assert_eq!(checked,381);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("stock","rustc","work",*REFS):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    raw=args.stock.read_bytes()
    identity(raw,BASE_BLOB,BASE_SHA)
    patch=Path(__file__).with_name("source.patch").read_bytes()
    check(hashlib.sha256(patch).hexdigest()==PATCH_SHA,"patch digest")
    changed=replay(raw,patch)
    identity(changed,AFTER_BLOB,AFTER_SHA)
    check(replay(changed,patch,reverse=True)==raw,"exact rollback")
    old,new=raw.decode(),changed.decode()
    anchor="pub(crate) fn output_text("
    check(old[old.index(anchor):]==new[new.index(anchor):],"untouched #268 fallback/body")
    refs={}
    for key,(blob,digest) in REFS.items():
        ref=getattr(args,key).read_bytes()
        identity(ref,blob,digest)
        refs[key]=ref.decode()
    dto_refs(refs)
    rustc=args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest()==RUSTC_SHA,"compiler digest")
    with tempfile.TemporaryDirectory(prefix="r247-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,
                                        text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        unit=root/"lift.rs"
        tests=prior_tests(refs["helpers"])
        unit.write_text(TESTS+"\n"+lift("stock",old,tests)+lift("candidate",new,tests),encoding="utf-8")
        results={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,
                            "-o",exe],check=True,cwd=root,env=env,timeout=90)
            run=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               capture_output=True,text=True,timeout=90)
            check(run.returncode==0,f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests_pass=re.search(r"test result: ok\. (\d+) passed; 0 failed;",run.stdout)
            counts=re.search(r"\bR247_ALLOC ((?:\d+ ){7}\d+)$",run.stdout,re.M)
            check(tests_pass is not None and int(tests_pass[1])==16,"test count")
            check(counts is not None,"allocation receipt")
            c=list(map(int,counts[1].split()))
            results[mode]={"tests_passed":int(tests_pass[1]),"generated_pairs":4096,
                           "stock_alloc_realloc_requested_bytes":c[:3],
                           "candidate_alloc_realloc_requested_bytes":c[3:6],
                           "single_final_capacity_stock_candidate_bytes":c[6:],
                           "multi_request_and_capacity_equal_pairs":381,
                           "multi_recognized_count_range":[2,128]}
    print(json.dumps({"status":"PASS","rustc":version,"rustc_sha256":RUSTC_SHA,
                      "locked_core":LOCKED_CORE,"exact_forward_and_reverse":True,
                      "prior_268_stock_postimages_attested":True,
                      "results":results,"real_provider_host_serde_or_cargo":False},indent=2))


if __name__=="__main__":
    main()
