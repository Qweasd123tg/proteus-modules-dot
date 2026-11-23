#!/usr/bin/env python3
"""Authenticate sources and test the exact normalizer and canonical builder offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

PATH = "workflow/coding-workflow/src/history.rs"
LOCKED_CORE = "0c1b7572313230e5d123e95c722e1258a2e9ecd6"
PINS = {
    "stock": ("c2db61e0b5cd07ff273b3c2cd2ffd2385d1dbb87", "126ed5558921e92286efe612b85efe9aa4def03f404021bf08bc8a5d8d580a86"),
    "candidate": ("c2c94e9d1b8d3714103350b8cceb3047a1536770", "d8c9a0e2deaf9ac0cdc208b18a3f65c333eb7399550880f4da6915a7d496b747"),
    "patch": ("4599dede312e07ceeda31be100f8fac507b035e3", "ae82af95b44a1b9975ca7ffded6359fa6ddf384f91a73e8acef05545b2d1467f"),
    "lock": ("ae7035fc5900b0afc480e55d2408c8234c88dd17", "0b4717cd37ba4b5848068f64c52e863000d8d7ea6d90464f4a134689e45bef54"),
    "content": ("9675ad69faa4e300aa5a00d8128f6992eeff4c57", "fe74614f707d36f73a63028af19ecfed2abc6cf2619080607f39d35f9aa974c0"),
    "tool": ("a4fb43299a3168511595ff7112e71b787cb2d23d", "94de0b99e3e161776eb0829dc9b83207d55afab0709d90de5fa968bcdd9e0e7c"),
    "ids": ("5ba1255896286e32754b87e25c91127d1faf42c7", "4b8c20657e1690a6f34891ab3f0b9081bef9b1781b6e784cecb7833c5ef4f07f"),
    "resumed-tests": ("aeb7d85e753e24878568d03a5efb7d5c06922000", "663b9ff87b976353ad6eb27ac851136cd9fb4787aa228f8145705ed58ca35794"),
    "codex-loop": ("b15650cd178696225b4de449a61cc63a5c587e02", "22160183269801a70a67658ae956a4ef183d292727da059555ea06ff680c85ff"),
    "scaffold": ("be45f061bc36b309d70de80855f850b0a7dceb29", "c54a3faa3df04e507a5b9947821cdf769e19240df8bb202536ce5c30d8484767"),
    "patch525": ("febb71d971c9d0fec307077725b03127d1a1f69c", "4ef8299c9d5cc2d1bc607a84af1d9419b8db99fa0d332fb4d623befbc7340a19"),
    "patch357": ("f5c74ba12d38d332cc1a34be5a03d6a49c7c623d", "caef621bff42bdf3562d3c3485269170ee380dd474e925368322491c77c59a5d"),
    "patch366": ("e8af4b997c425f5f0ed175609b88d06bbdb6f6aa", "927b398bb22e8f00cf4a77fc39f1f09228644655667ac0a8564fddf14da26a79"),
}
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(tag, data):
    git = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    check((git, sha(data)) == PINS[tag], f"identity: {tag}")


def replay(src, patch, reverse=False):
    header = (f"diff --git a/{PATH} b/{PATH}\n"
              f"index {PINS['stock'][0]}..{PINS['candidate'][0]} 100644\n"
              f"--- a/{PATH}\n+++ b/{PATH}\n").encode()
    check(patch.startswith(header), "single target")
    hunk = patch[len(header):].splitlines(keepends=True)
    check(hunk[0] == b"@@ -21,7 +21,7 @@\n" and len(hunk) == 9, "one-line hunk")
    check([l[1:].strip() for l in hunk[1:] if l[:1] == b"-"] ==
          [b"ContentPart::ToolResult { result } => Some(result.call_id.clone()),"], "old expression")
    check([l[1:].strip() for l in hunk[1:] if l[:1] == b"+"] ==
          [b"ContentPart::ToolResult { result } => Some(&result.call_id),"], "new expression")
    old, new = ([l[1:] for l in hunk[1:] if l[:1] != skip] for skip in (b"+", b"-"))
    if reverse:
        old, new = new, old
    lines = src.splitlines(keepends=True)
    check(lines[20:27] == old, "exact context")
    return b"".join(lines[:20] + new + lines[27:])


def cut(text, start, end):
    tail = text.split(start, 1)[1]
    return start + tail.split(end, 1)[0]


def sdk_projection(refs):
    tool, content, ids = (refs[k] for k in ("tool", "content", "ids"))
    id_line = re.search(r"(?m)^pub type CallId = String;$", ids)[0]
    call = cut(tool, "pub struct ToolCall {", "    pub fn with_surface(") + "}\n"
    surface = cut(tool, "pub enum ToolCallSurface {", "impl ToolCallSurface")
    result = cut(tool, "pub struct ToolResult {", "    /// Полный конструктор") + "}\n"
    result_content = cut(tool, "pub enum ToolContent {", "\n}\n") + "\n}\n"
    declarations = cut(content, "#[derive(Debug, Clone, Serialize", "\nimpl CanonicalMessage")
    declarations = re.sub(r"(?m)^#\[serde\([^\n]+\)\]\n", "", declarations)
    declarations = declarations.replace(", Serialize, Deserialize", "")
    constructors = (
        "impl CanonicalMessage {\n"
        + cut(content, "    pub fn text(role: MessageRole", "    pub fn with_id(mut self, id: MessageId)")
        + cut(content, "    pub fn with_tool_call_id(mut self", "\n    }") + "\n    }\n}\n"
        + cut(content, "fn default_part_semantics(", "#[cfg(test)]")
    )
    for sig in ("pub id: CallId", "pub call_id: CallId", "pub tool_call_id: Option<CallId>",
                "ContentPart::ToolResult { .. } | ContentPart::Patch { .. }"):
        check(sig in "\n".join((call, result, declarations, constructors)), f"SDK shape {sig}")
    return (id_line + "\n#[derive(Debug,Clone,PartialEq)]\n" + call
            + "#[derive(Debug,Clone,Copy,PartialEq,Eq,Default)]\n" + surface
            + "#[derive(Debug,Clone,PartialEq)]\n" + result_content
            + "#[derive(Debug,Clone,PartialEq)]\n" + result + declarations + constructors)


def lift(tag, source, test_ref):
    body = cut(source, "pub(crate) fn tool_result_message(", "pub(crate) fn current_user_index(")
    classify = source[source.index("fn is_ephemeral_context_message("):]
    exact_test = cut(test_ref, "fn missing_outputs_preserve_real_results_order_and_are_idempotent(",
                     "#[test]\nfn codex_interruption_marker")
    exact_test = exact_test.replace("crate::history::tool_result_message(", "tool_result_message(")
    result_lookup = cut(test_ref, "fn results_for<'a>(", "fn assert_resumed(")
    return (f"mod {tag} {{\nuse super::*;\nuse std::collections::HashSet;\n" + body
            + "pub(super) " + classify + result_lookup + "#[test]\n" + exact_test + "}\n")


STUB = r'''
use std::alloc::{GlobalAlloc,Layout,System};
use std::cell::Cell;
use std::hint::black_box;
use std::path::PathBuf;

type MessageId=u128;
type PartId=u128;
type Citation=String;
type ContextChunk=String;
type HostedToolActivity=String;
type Patch=String;
thread_local! { static NEXT_ID:Cell<u128>=const {Cell::new(1)}; }
fn next_id()->u128 { NEXT_ID.with(|x| {let id=x.get(); x.set(id+1); id}) }
mod domain {
    pub type ImageRef=String;
    pub fn new_message_id()->u128 {super::next_id()}
    pub fn new_part_id()->u128 {super::next_id()}
}
mod serde_json {
    #[derive(Debug,Clone,PartialEq)]
    pub enum Value {Null,Path(String)}
}
macro_rules! json {
    ({"path": $id:ident})=>{ serde_json::Value::Path($id.to_string()) };
}
'''

TESTS = r'''
type Normalize=fn(&mut Vec<CanonicalMessage>);
fn call(id: &str)->ContentPart {
    ContentPart::ToolCall {call:ToolCall::new(id,"inert",serde_json::Value::Null)}
}
fn completed(id: &str, ok: bool)->ContentPart {
    let result=if ok {ToolResult::ok(id.into(),"opaque result")} else {ToolResult::error(id.into(),"real error")};
    ContentPart::ToolResult {result}
}
fn assistant(parts: Vec<ContentPart>)->CanonicalMessage {CanonicalMessage::new(MessageRole::Assistant,parts)}
fn make_result(id: &str, ok: bool)->CanonicalMessage {
    let ContentPart::ToolResult {result}=completed(id,ok) else {unreachable!()};
    stock::tool_result_message(result)
}
fn matches_synthetic(row: &CanonicalMessage,id: &str) {
    assert_eq!(row.role,MessageRole::Tool);
    assert_eq!(row.tool_call_id.as_deref(),Some(id));
    assert_eq!(row.parts.len(),1);
    assert_eq!(row.parts[0].provenance,PartProvenance::Tool);
    assert_eq!(row.parts[0].scope,PartScope::Request);
    assert_eq!(row.parts[0].payload,ContentPart::ToolResult{result:ToolResult::error(id.into(),"aborted")});
    assert!(stock::is_ephemeral_context_message(row) && candidate::is_ephemeral_context_message(row));
}
fn normalize_pair(input: &[CanonicalMessage])->Vec<CanonicalMessage> {
    let (mut a,mut b)=(input.to_vec(),input.to_vec());
    NEXT_ID.set(1_000_000_000);
    stock::normalize_missing_tool_outputs(&mut a);
    NEXT_ID.set(1_000_000_000);
    candidate::normalize_missing_tool_outputs(&mut b);
    assert_eq!(a,b);
    for (f, rows) in [(stock::normalize_missing_tool_outputs as Normalize,&mut a),
                      (candidate::normalize_missing_tool_outputs as Normalize,&mut b)] {
        let once=rows.clone();
        f(rows);
        assert_eq!(*rows,once);
    }
    b
}

#[test]
fn multirow_reverse_insertion_does_not_reverse_original_call_order() {
    let a=assistant(vec![call("a"),call("b"),call("a"),call("c")]);
    let b=assistant(vec![call("d"),call("c"),call("é"),call("e\u{301}")]);
    let result=make_result("b",false);
    let no_parts=CanonicalMessage::new(MessageRole::System,vec![]);
    let tail=CanonicalMessage::text(MessageRole::User,"continue");
    let seed=vec![a.clone(),result.clone(),no_parts.clone(),b.clone(),tail.clone()];
    let out=normalize_pair(&seed);
    assert_eq!(out.len(),12);
    assert_eq!(out[0],a);
    assert_eq!(&out[4..7], &[result,no_parts,b]);
    assert_eq!(out[11],tail);
    for (index,id) in [(1,"a"),(2,"a"),(3,"c"),(7,"d"),(8,"c"),(9,"é"),(10,"e\u{301}")] {
        matches_synthetic(&out[index],id);
    }
}

#[test]
fn membership_remains_global_only_by_payload_id_not_scope_or_top_level() {
    let mut prior=CanonicalMessage::new(MessageRole::User,vec![completed("",true),completed("x",false)]);
    prior.parts[0].scope=PartScope::Trace;
    prior.parts[1].scope=PartScope::Request;
    let calls=assistant(vec![call(""),call("x"),call("X"),call("β")]);
    let late=CanonicalMessage::new(MessageRole::Developer,vec![completed("β",true),completed("β",false)])
        .with_tool_call_id("X".into());
    let seed=vec![prior.clone(),calls.clone(),late.clone()];
    let out=normalize_pair(&seed);
    assert_eq!(out.len(),4);
    assert_eq!(&out[..2],&[prior,calls]);
    matches_synthetic(&out[2],"X");
    assert_eq!(out[3],late);
    assert!(normalize_pair(&[]).is_empty());
}

#[test]
fn builder_preserves_owned_call_id_and_existing_result_fields() {
    let mut result=ToolResult::ok("a\0é".into(),"full result");
    result.content.push(ToolContent::Binary{mime_type:"inert".into(),data:"fixture".into()});
    result.metadata=serde_json::Value::Path("marker".into());
    NEXT_ID.set(500_000_000);
    let a=stock::tool_result_message(result.clone());
    NEXT_ID.set(500_000_000);
    let b=candidate::tool_result_message(result.clone());
    assert_eq!(a,b);
    assert_eq!(b.parts[0].scope,PartScope::Conversation);
    assert_eq!(b.parts[0].payload,ContentPart::ToolResult{result});
    assert_eq!(b.tool_call_id.as_deref(),Some("a\0é"));
    assert!(!candidate::is_ephemeral_context_message(&b));
    if let ContentPart::ToolResult {result}=&b.parts[0].payload {
        assert_ne!(b.tool_call_id.as_ref().unwrap().as_ptr(),result.call_id.as_ptr());
    }
}

#[test]
fn generated_histories_equal_and_preserve_observed_roles_payloads_and_order() {
    let ids=["","a","A","a "," a","é","e\u{301}","😀","\0","\t","aborted"];
    let mut rng=72491_u64;
    let mut next=|n:usize| {
        rng=rng.wrapping_mul(6364136223846793005).wrapping_add(1); ((rng>>32) as usize)%n
    };
    for _ in 0..4096 {
        NEXT_ID.set(1);
        let mut initial=Vec::new();
        for _ in 0..next(10) {
            let mut parts=Vec::new();
            for _ in 0..next(10) {
                let id=ids[next(ids.len())];
                parts.push(match next(6) {
                    0|1=>call(id),2=>completed(id,true),3=>completed(id,false),
                    4=>ContentPart::Text{text:id.into()},
                    _=>ContentPart::Opaque{format:"fixture".into(),data:serde_json::Value::Null},
                });
            }
            let mut row=CanonicalMessage::new([MessageRole::User,MessageRole::Assistant,MessageRole::Tool][next(3)].clone(),parts);
            for p in &mut row.parts {p.scope=[PartScope::Conversation,PartScope::Request,PartScope::Trace][next(3)];}
            row.tool_call_id=(next(2)==0).then(|| ids[next(ids.len())].into());
            initial.push(row);
        }
        let rows=normalize_pair(&initial);
        let complete:Vec<&str>=initial.iter().flat_map(|r| &r.parts).filter_map(|p|
            if let ContentPart::ToolResult {result}=&p.payload {Some(result.call_id.as_str())} else {None}).collect();
        let mut out=rows.iter();
        for old in &initial {
            assert_eq!(out.next(),Some(old));
            for part in &old.parts {
                if let ContentPart::ToolCall {call}=&part.payload && !complete.contains(&call.id.as_str()) {
                    matches_synthetic(out.next().unwrap(),&call.id);
                }
            }
        }
        assert!(out.next().is_none());
    }
}

#[derive(Clone,Copy,Debug,Default)]
struct Stat {alloc:usize,realloc:usize,bytes:usize}
thread_local! { static METER:Cell<Option<Stat>>=const {Cell::new(None)}; }
fn request(bytes:usize,re:bool) {
    let _=METER.try_with(|m| {
        if let Some(mut s)=m.get() {
            if re {s.realloc+=1;} else {s.alloc+=1;}
            s.bytes+=bytes; m.set(Some(s));
        }
    });
}
struct Tracker;
unsafe impl GlobalAlloc for Tracker {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {request(l.size(),false); unsafe {System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {request(l.size(),false); unsafe {System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {request(n,true); unsafe {System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout) {unsafe {System.dealloc(p,l)}}
}
#[global_allocator]
static ALLOCATOR:Tracker=Tracker;
fn meter(f: Normalize, rows:&mut Vec<CanonicalMessage>)->Stat {
    assert!(METER.replace(Some(Stat::default())).is_none());
    black_box(f)(black_box(rows));
    METER.take().unwrap()
}

#[test]
fn completed_125k_history_scoped_allocation_requests() {
    let pairs=62_499;
    let mut history=Vec::with_capacity(125_000);
    history.push(CanonicalMessage::text(MessageRole::User,"previous"));
    for i in 0..pairs {
        let id=format!("call-{i:059}");
        assert_eq!(id.len(),64);
        history.push(assistant(vec![call(&id)]));
        history.push(make_result(&id,i%2==0));
        if let ContentPart::ToolCall{call}=&history[history.len()-2].parts[0].payload
            && let ContentPart::ToolResult{result}=&history[history.len()-1].parts[0].payload {
            assert_eq!(call.id,result.call_id);
            assert_ne!(call.id.as_ptr(),result.call_id.as_ptr());
        } else {unreachable!();}
    }
    history.push(CanonicalMessage::text(MessageRole::User,"current"));
    assert_eq!(history.len(),125_000);
    let mut a=history.clone();
    let mut b=history.clone();
    let old=meter(stock::normalize_missing_tool_outputs,&mut a);
    let new=meter(candidate::normalize_missing_tool_outputs,&mut b);
    assert_eq!(a,history);
    assert_eq!(b,history);
    assert_eq!(old.alloc-new.alloc,pairs);
    assert_eq!(old.realloc,new.realloc);
    assert!(old.bytes-new.bytes>=64*pairs);
    println!("R249_ALLOC {} {} {} {} {} {}",old.alloc,old.realloc,old.bytes,new.alloc,new.realloc,new.bytes);
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("refs", "work", "rustc"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    refs = {}
    for tag in PINS:
        if tag not in ("candidate", "patch"):
            raw = (args.refs / (tag + ".ref")).read_bytes()
            identity(tag, raw)
            refs[tag] = raw.decode()
    lock_source = next(part for part in refs["lock"].split("[[package]]")
                       if '\nname = "proteus-contracts"\n' in part)
    check(f"?rev={LOCKED_CORE}#{LOCKED_CORE}" in lock_source, "locked SDK revision")
    check("normalize_missing_tool_outputs(&mut turn.model_messages)" in refs["scaffold"]
          and "normalize_missing_tool_outputs(&mut turn.model_messages)" in refs["codex-loop"], "actual callers")
    for tag, expected in (
        ("patch525", ["hook/codex-context-preparation/src/recovery.rs"]),
        ("patch357", ["workflow/coding-workflow/src/scaffold.rs", "workflow/coding-workflow/src/scaffold/history_tests.rs"]),
        ("patch366", ["workflow/coding-workflow/src/host.rs", "workflow/coding-workflow/src/tests/request_accounting.rs"]),
    ):
        check(re.findall(r"(?m)^\+\+\+ b/(\S+)$", refs[tag]) == expected, f"disjoint targets: {tag}")
    patch = Path(__file__).with_name("source.patch").read_bytes()
    identity("patch", patch)
    stock = refs["stock"].encode()
    candidate = replay(stock, patch)
    identity("candidate", candidate)
    check(replay(candidate, patch, reverse=True) == stock, "exact rollback")
    rustc = args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes()) == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r249-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH":"/usr/bin:/bin", "HOME":temp, "TMPDIR":temp, "LC_ALL":"C"}
        version = subprocess.check_output([rustc,"--version"],cwd=root,env=env,text=True,timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        unit = root / "lift.rs"
        unit.write_text(STUB + sdk_projection(refs) +
                        lift("stock", refs["stock"], refs["resumed-tests"]) +
                        lift("candidate", candidate.decode(), refs["resumed-tests"]) + TESTS, encoding="utf-8")
        result = {}
        for mode, flags in [("debug",[]),("optimized",["-O"])]:
            exe=root / ("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,"-o",exe],
                           check=True,cwd=root,env=env,timeout=90)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               capture_output=True,text=True,timeout=90)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 7 passed; 0 failed;" in out.stdout,"test count")
            counts=re.search(r"(?m)\bR249_ALLOC ((?:\d+ ){5}\d+)$",out.stdout)
            check(counts is not None,"allocation receipt")
            n=list(map(int,counts[1].split()))
            result[mode]={"tests_passed":7,"generated_exact_output_pairs":4096,
                          "allocation_fixture_messages":125000,"completed_distinct_ids":62499,
                          "stock_alloc_realloc_requested_bytes":n[:3],"candidate_alloc_realloc_requested_bytes":n[3:]}
    print(json.dumps(dict(status="PASS",rustc=version,rustc_sha256=RUSTC_SHA,locked_core=LOCKED_CORE,
                          exact_apply_reverse=True,results=result),indent=2))


if __name__=="__main__":
    main()
