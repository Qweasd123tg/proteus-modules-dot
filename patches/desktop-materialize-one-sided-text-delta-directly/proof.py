#!/usr/bin/env python3
"""Replay the Desktop text-run patch and verify scoped text folding offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

PATH = "src/transcript/text_run.rs"
TEST_PATH = "src/transcript/text_run/tests.rs"
PINS = {
    "stock": ("1061f2221ef432e4bab1488673d2276beb2091f7", "1c9cf00c31340e4404c7c55e02cdaf3c36e2ec214ccf5298eee5804da2ce3c90"),
    "candidate": ("b622b00ede37abd3276c683226cdd469c40166d5", "81b1eb4254003130836ef56ba491f948325315e2fd3154acfa4a84e0ed149b2b"),
    "tests": ("6c31bcdc06a15fc1a43b1d194a95b3aae2d32a00", "34d8e0313f22de86223dc8902f9edd234d1435a0fc4385628eed970ce103ce31"),
    "tests-next": ("4938d93544bde27a1849293d979a3dc94a130927", "cbeed069aceb51582bee3bd052b3b7b318a394163bb1b318e197e34df296e277"),
    "prior": ("d0d370917263d9bd08bd8ad16c0a21f083bf9211", "3b3eb035ebd4ef03453ad7bd37159b9932caf9b7a060e313f748cb8f044cc10f"),
    "transcript": ("b2c3333b89aa4d3197c27835c5a6d51fe500b44e", "d6a0e1720e2b588f5afd6ab3ca59ec21bd2913a0ebeed0a1209312156a76f3cf"),
    "patch": ("631a0f045109347be972219c310e70101d382dfc", "129d6cf044ed520c529ef0952bb68144669d888be05c6d55c0e7fea3e965a565"),
}
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"


def check(ok, label):
    if not ok:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(tag, raw):
    check((hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest(), sha(raw))
          == PINS[tag], f"identity: {tag}")


def patch_header(path, before, after):
    return (f"diff --git a/{path} b/{path}\n"
            f"index {PINS[before][0]}..{PINS[after][0]} 100644\n"
            f"--- a/{path}\n+++ b/{path}\n").encode()


def replay(raw, patch, header, count, reverse=False):
    check(patch.startswith(header), "diff file")
    hunks = re.split(rb"(?m)(^@@ [^\n]+\n)", patch[len(header):])
    check(hunks[0] == b"" and len(hunks) == 1 + 2 * count, "hunk count")
    source = raw.splitlines(keepends=True)
    line = 0
    target = []
    for label, body in zip(hunks[1::2], hunks[2::2]):
        match = re.fullmatch(rb"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n", label)
        check(match is not None, "hunk coordinates")
        a, n, b, m = map(int, match.groups())
        rows = body.splitlines(keepends=True)
        check(all(r[:1] in (b" ", b"-", b"+") for r in rows), "hunk rows")
        old, new = ([r[1:] for r in rows if r[:1] != skip] for skip in (b"+", b"-"))
        check((len(old), len(new)) == (n, m), "hunk lengths")
        if reverse:
            a, b = b, a
            old, new = new, old
        check(line <= a - 1 and source[a-1:a-1+len(old)] == old, "exact input hunk")
        target.extend(source[line:a-1])
        check(len(target) == b - 1, "exact output offset")
        target.extend(new)
        line = a - 1 + len(old)
    return b"".join(target + source[line:])


def part(s, begin, end=None):
    at = s.index(begin)
    return s[at:] if end is None else s[at:s.index(end, at + len(begin))]


def test_code(tests):
    # Keep the exact matrix, outcome tests and added regression; replace only the
    # general fixture/metadata serialization with inert shape-equivalent setup.
    return (part(tests, "fn event(", "fn assert_entry(")
            + part(tests, "fn assert_transcript(", "#[test]\nfn reverse_identity_lookup")
            + part(tests, "#[test]\nfn foreign_root_run"))


def variant(tag, source, tests, parent):
    exact_types = part(parent, "#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]",
                       "#[derive(Default, Clone)]\npub struct Transcript")
    single = part(parent, "            Event::AssistantTextDelta {",
                  "            Event::AssistantMessageCompleted {")
    exact_helpers = ("impl Transcript {\n"
                     + part(parent, "    pub fn set_root_thread", "    pub fn entries(")
                     + part(parent, "    pub fn stamp", "    pub fn apply_runtime")
                     + "    fn apply_runtime(&mut self, thread_id: ThreadId, event: &Event) -> Change {\n        match event {\n"
                     + single + "            _ => Change::None,\n        }\n    }\n"
                     + part(parent,"    fn is_turn_thread", "    fn running_subagent")
                     + part(parent,"    fn stop_streaming", "    fn entry_from(")
                     + "}\n" + part(parent, "fn delta_keep(", "fn finish_tool("))
    verify = test_code(tests)
    start = source.index("/// Only compatible text events")
    text_run = source[start:source.rindex("#[cfg(test)]\nmod tests;")]
    return (f"#[allow(dead_code)]\nmod {tag} {{\nuse super::*;\n" + exact_types
            + TRANSCRIPT + exact_helpers + "mod text_run {\nuse super::*;\n" + text_run
            + "mod tests {\nuse super::*;\n" + FIXTURE + verify + "}\n"
            + MEASURE_FINISH + "}\npub(super) use text_run::measure_finish;\n}\n")


STUB = r'''
use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
use std::hint::black_box;
use std::sync::{Arc, atomic::{AtomicU64,Ordering}};

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
struct Uuid(u128);
impl Uuid {
    fn from_u128(value:u128)->Self {Self(value)}
}
fn id(value:u128)->Uuid {Uuid::from_u128(value)}
type MessageId=Uuid;
type ThreadId=Uuid;
type ImageRef=String;
type AppTranscriptTool=String;
type AppTranscriptSubagent=String;
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
#[allow(dead_code)]
enum MessagePhase { Commentary, FinalAnswer }
#[derive(Clone,Debug)]
#[allow(dead_code)]
enum Event {
    AssistantTextDelta {offset:usize,message_id:MessageId,phase:Option<MessagePhase>,text:String},
    Other,
}
struct EventContext {session_id:Uuid,thread_id:Uuid,turn_id:Option<Uuid>}
impl EventContext {
    fn new(session_id:Uuid,thread_id:Uuid,turn_id:Option<Uuid>)->Self {Self{session_id,thread_id,turn_id}}
}
#[derive(Clone,Debug)]
struct EventEnvelope {
    schema_version:u32, session_id:Uuid, thread_id:Uuid,turn_id:Option<Uuid>,
    event_id:Uuid,timestamp_ms:i64,event:Event,
}
impl EventEnvelope {
    fn new(ctx:EventContext,_seq:u64,event:Event)->Self {
        Self {schema_version:1,session_id:ctx.session_id,thread_id:ctx.thread_id,turn_id:ctx.turn_id,
              event_id:Uuid(0),timestamp_ms:0,event}
    }
}
#[derive(Clone,Debug)]
#[allow(dead_code)]
enum AppServerEvent {Runtime {envelope:Box<EventEnvelope>}, Barrier}
'''

TRANSCRIPT = r'''
#[derive(Default)]
struct Transcript {
    entries: Vec<Entry>,
    turn_thread: Option<ThreadId>,
    snapshot_root_known: bool,
    next_key: Arc<AtomicU64>,
    text_work: text_run::TextWork,
}
'''

FIXTURE = r'''
fn fixture(base:Option<&str>)->Transcript {
    let mut transcript=Transcript::default();
    let mut push=|value, text: &str, time, streaming| {
        let key=transcript.allocate_key();
        transcript.entries.push(Entry { key,message_id:Some(id(value)),role:Role::Assistant,
            text:text.into(),images:vec![],tool:None,subagent:None,streaming,time });
    };
    push(200,"other row",Some(7),true);
    if let Some(base)=base { push(100,base,None,false); }
    transcript.set_root_thread(Some(id(10)));
    transcript
}
fn assert_entry(a:&Entry,b:&Entry) {
    assert_eq!((a.key,a.message_id,a.role,&a.text,&a.images,&a.tool,&a.subagent,a.streaming,a.time),
               (b.key,b.message_id,b.role,&b.text,&b.images,&b.tool,&b.subagent,b.streaming,b.time));
}
'''

MEASURE_FINISH = r'''
pub(crate) fn measure_finish(base: &str, operations:&[(usize,&str)])->(Arc<str>,Stats) {
    let mut edit=DeltaEdit::new(black_box(base));
    for (offset,text) in operations {edit.apply(*offset,text);}
    measured(|| black_box(edit).finish())
}
'''

TESTS = r'''
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Stats { alloc:usize, realloc:usize, bytes:usize }
thread_local! { static SAMPLE:Cell<Option<Stats>>=const {Cell::new(None)}; }
fn request(n:usize,re:bool) {
    let _=SAMPLE.try_with(|cell| if let Some(mut state)=cell.get() {
        if re {state.realloc+=1;} else {state.alloc+=1;}
        state.bytes+=n;cell.set(Some(state));
    });
}
struct Allocator;
unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {request(n,true);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout) { unsafe{System.dealloc(p,l)} }
}
#[global_allocator]
static ALLOCATOR:Allocator=Allocator;
fn measured(f:impl FnOnce()->Arc<str>)->(Arc<str>,Stats) {
    assert!(SAMPLE.replace(Some(Stats::default())).is_none());
    let row=black_box(f());
    (row,SAMPLE.take().unwrap())
}
#[test]
fn finish_fresh_empty_and_equal_nonempty_arc_identity() {
    for base in ["","é","x🦀"] {
        let original:Arc<str>=base.into();
        for ops in [vec![],vec![(0,base)],vec![(0,""),(0,base)]] {
            let before=stock::measure_finish(&original,&ops).0;
            let after=candidate::measure_finish(&original,&ops).0;
            assert_eq!(before,original);
            assert_eq!(after,original);
            assert!(!Arc::ptr_eq(&original,&before));
            assert!(!Arc::ptr_eq(&original,&after));
            assert!(!Arc::ptr_eq(&before,&after));
            assert_eq!(Arc::strong_count(&original),1);
            assert_eq!(Arc::strong_count(&after),1);
        }
    }
}
#[test]
fn megabyte_fixtures_only_measure_finish_requests() {
    let mib=1<<20;
    let tail="é".repeat(mib/2);
    let base:Arc<str>="a".repeat(mib+1).into();
    let head="b".repeat(mib/2);
    let mixed=format!("{}{head}",&base[..mib/2]);
    for (label,ops,expected,removed) in [
        ("tail",vec![(0,tail.as_str())],tail.as_str(),mib),
        ("prefix",vec![(mib,"scratch"),(mib,"")],&base[..mib],mib),
        ("mixed",vec![(mib/2,head.as_str())],mixed.as_str(),0),
        ("empty",vec![(0,"")],"",0),
    ] {
        let (a,old)=stock::measure_finish(&base,&ops);
        let (b,new)=candidate::measure_finish(&base,&ops);
        assert_eq!(&*a,expected);
        assert_eq!(a,b);
        assert!(!Arc::ptr_eq(&a,&b));
        assert!(!Arc::ptr_eq(&base,&b));
        assert_eq!(old.realloc,new.realloc);
        assert_eq!(old.bytes-new.bytes,removed);
        assert_eq!(old.alloc-new.alloc,usize::from(removed>0));
        println!("R250_ALLOC {label} {} {} {} {} {} {}",old.alloc,old.realloc,old.bytes,new.alloc,new.realloc,new.bytes);
    }
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("refs","work","rustc"):
        p.add_argument("--"+k,type=Path,required=True)
    args = p.parse_args()
    refs = {}
    for k in ("stock","tests","transcript","prior"):
        refs[k] = (args.refs/(k+".ref")).read_bytes()
        identity(k,refs[k])
    prior = refs["prior"].decode()
    for path, tag in ((PATH,"stock"),(TEST_PATH,"tests")):
        old_post = re.search(rf"(?m)^diff --git a/{re.escape(path)} b/{re.escape(path)}\nindex [0-9a-f]+\.\.([0-9a-f]+) 100644$",prior)
        check(old_post is not None and PINS[tag][0].startswith(old_post[1]), "#354 already in stock")
    patch=Path(__file__).with_name("source.patch").read_bytes()
    identity("patch",patch)
    test_header=patch_header(TEST_PATH,"tests","tests-next")
    split=patch.index(test_header)
    next_refs={}
    for before,after,part_,hdr,cnt in [
        ("stock","candidate",patch[:split],patch_header(PATH,"stock","candidate"),2),
        ("tests","tests-next",patch[split:],test_header,1),
    ]:
        next_refs[after]=replay(refs[before],part_,hdr,cnt)
        identity(after,next_refs[after])
        check(replay(next_refs[after],part_,hdr,cnt,True)==refs[before],"full rollback")
    rustc=args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC_SHA,"compiler identity")
    with tempfile.TemporaryDirectory(prefix="r250-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        file=root/"lift.rs"
        parent=refs["transcript"].decode()
        file.write_text(STUB+variant("stock",refs["stock"].decode(),refs["tests"].decode(),parent)
            +variant("candidate",next_refs["candidate"].decode(),next_refs["tests-next"].decode(),parent)+TESTS,encoding="utf-8")
        results={}
        for mode, flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,file,"-o",exe],
                           check=True,cwd=root,env=env,timeout=120)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               capture_output=True,text=True,timeout=120)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 23 passed; 0 failed;" in out.stdout,"exact test count")
            scopes={}
            for label, values in re.findall(r"(?m)\bR250_ALLOC (\w+) ((?:\d+ ){5}\d+)$",out.stdout):
                counters=list(map(int,values.split()))
                scopes[label]={"stock_alloc_realloc_requested_bytes":counters[:3],
                               "candidate_alloc_realloc_requested_bytes":counters[3:]}
            check(set(scopes)=={"tail","prefix","mixed","empty"},"allocation receipts")
            results[mode]={"tests_passed":23,"small_utf8_matrix_partition_cases_per_arm":387072,
                           "allocations_scope":"finish only, with fixture and editing before meter",
                           "allocations":scopes}
    print(json.dumps(dict(status="PASS",rustc=version,rustc_sha256=RUSTC_SHA,exact_apply_reverse=True,
                          prior_354_already_adopted=True,results=results),indent=2))


if __name__=="__main__":
    main()
