#!/usr/bin/env python3
"""Replay the exact patch and verify the Rust 1.95 diagnostic prefix and final prompt."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


PATH = "workflow/coding-workflow/src/project_check.rs"
BASE_BLOB = "0c7b892f84e610be838a25032104266f4d7f4487"
BASE_SHA = "237bd65e5350e555540471e472621a1e4b3ba13b3e249db6da9dff8a4c6f4e6d"
AFTER_BLOB = "42b819543daf3dc582818d834bc89988b1708e16"
AFTER_SHA = "d5e82a55a29903b89692f85790070065c976c354dcd52918af20a8ae27154ac5"
PATCH_SHA = "a93cb3280da30288080bf3c4561a2fa9078c376140911507fcfa1a9ca957bb35"


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
    check(count == 2, "expected prompt/private helper and existing fixture hunks")
    return b"".join(target + lines[used:])


def section(source, first, end):
    at = source.index(first)
    return source[at:source.index(end, at + len(first))]


RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
LOCKED_CORE = "0c1b7572313230e5d123e95c722e1258a2e9ecd6"
REFS = {
    "lock": ("ae7035fc5900b0afc480e55d2408c8234c88dd17",
             "0b4717cd37ba4b5848068f64c52e863000d8d7ea6d90464f4a134689e45bef54"),
    "sdk": ("81926d05039949d3e5eacc3843c8f825788b9e2e",
            "6a323d6d8ffadb6708b0e40a629daf78a486f74f3b7660b2c4bfab722573464d"),
    "tool": ("a4fb43299a3168511595ff7112e71b787cb2d23d",
             "94de0b99e3e161776eb0829dc9b83207d55afab0709d90de5fa968bcdd9e0e7c"),
    "task": ("92e6a3643f4312cfa5a0dc21022669955a467d5e",
             "822378f15849018d47ded7c66ada482e2856b8433d5eb94378b04b3ce22e2924"),
}
PROMPT = "fn diagnostic_prompt("
AFTER_PROMPT = "\nstruct CheckReport {"
TESTS_MARK = "#[cfg(test)]\nmod tests {"
TEST_MARK = "    fn diagnostic_bounding_preserves_utf8() {"


def lift(name, code, revised):
    cap = re.search(r"^const MAX_DIAGNOSTIC_CHARS: usize = .+;$", code, re.M)
    check(cap is not None and cap[0] == "const MAX_DIAGNOSTIC_CHARS: usize = 12_000;",
          "exact production cap")
    struct = section(code, "#[derive(Clone, Copy, Debug, PartialEq, Eq)]\nstruct ProjectDefinition",
                     "\n];") + "\n];"
    pure = section(code, "fn detect_project(", AFTER_PROMPT)
    native_tests = code[code.index(TESTS_MARK):]
    probe = ('pub(super) fn cap_parts(s: &str, n: usize) -> (&str, &\'static str) { bounded_text(s, n) }'
             if revised else
             'pub(super) fn cap_flat(s: &str, n: usize) -> String { bounded_text(s, n) }')
    return (f"mod {name} {{\nuse crate::*;\n" + cap[0] + "\n" + struct + "\n" + pure
            + native_tests + "\n" + probe + r'''
pub(super) fn render(input: &WorkflowModuleInput, project: usize, dirty: bool, output: &ToolResult) -> String {
    diagnostic_prompt(input, PROJECTS[project], dirty, output)
}
pub(super) fn names() -> [(&'static str,&'static str,&'static str);4] {
    PROJECTS.map(|p| (p.kind,p.marker,p.command))
}
pub(super) fn dirty(s: &str) -> bool { git_status_is_dirty(s) }
}
''')


def projected_types(refs):
    lock = re.search(r'\[\[package\]\]\nname = "proteus-contracts"\n[^\[]+', refs["lock"])
    check(lock is not None and f"?rev={LOCKED_CORE}#{LOCKED_CORE}" in lock[0], "locked SDK")
    dto = []
    for label, name, fields in [
        ("sdk", "WorkflowModuleInput", ["pub task: AgentTask,"]),
        ("task", "AgentTask", ["pub text: String,"]),
        ("tool", "ToolResult", ["pub output: String,", "pub error: Option<String>,"]),
    ]:
        src = refs[label]
        struct = section(src, f"pub struct {name} {{", "\n}")
        check(all(f"    {f}" in struct for f in fields), f"exact {name} projected fields")
        dto.append(f"struct {name} {{\n    " + "\n    ".join(fields) + "\n}\n")
    return "".join(dto)


TESTS = r'''
use std::{alloc::{GlobalAlloc,Layout,System},cell::Cell,hint::black_box};
const SUFFIX:&str="\n[diagnostics truncated]";
const OUT_HEADER:&str="\n\nCommand output:\n";

fn check_parts(text:&str,limit:usize)->(&str,&'static str) {
    let (prefix,suffix)=candidate::cap_parts(text,limit);
    let old=stock::cap_flat(text,limit);
    assert_eq!(old.as_bytes(), [prefix.as_bytes(),suffix.as_bytes()].concat());
    assert_eq!(prefix.as_ptr(),text.as_ptr());
    assert!(prefix.len()<=text.len() && text.is_char_boundary(prefix.len()));
    let oracle=text.chars().take(limit).collect::<String>();
    assert_eq!(oracle.as_bytes(),prefix.as_bytes());
    assert_eq!(suffix,if prefix.len()<text.len() {SUFFIX} else {""});
    (prefix,suffix)
}
fn pair(input:&WorkflowModuleInput,project:usize,dirty:bool,tool:&ToolResult)->String {
    let a=stock::render(input,project,dirty,tool);
    let b=candidate::render(input,project,dirty,tool);
    assert_eq!(a.as_bytes(),b.as_bytes(),"full prompt bytes");
    b
}
fn input(text:&str)->WorkflowModuleInput { WorkflowModuleInput { task:AgentTask { text:text.into() } } }
fn tool(output:&str,error:Option<&str>)->ToolResult {
    ToolResult { output:output.into(),error:error.map(str::to_owned) }
}

#[test]
fn exact_full_prompt_text_for_all_projects_errors_and_git_states() {
    let request=input("исходная задача\r\n🧪\0");
    let projects=stock::names();
    assert_eq!(projects,candidate::names());
    for (i,(kind,marker,cmd)) in projects.into_iter().enumerate() {
        for (status,dirty,state) in [
            ("## clean branch\n",false,"чистое"),
            ("## branch\n M example.rs",true,"есть изменения")
        ] {
            assert_eq!(stock::dirty(status),dirty);
            assert_eq!(candidate::dirty(status),dirty);
            for error in [None,Some(""),Some("opaque\r\nошибка\0")] {
                let out="ข้อความ\r\n\t漢字\0";
                let result=tool(out,error);
                let got=pair(&request,i,dirty,&result);
                let err=error.unwrap_or("<none>");
                let expected=format!("Original task:\nисходная задача\r\n🧪\0\n\nProject kind: {kind}\nMarker: {marker}\nCommand: {cmd}\nGit working tree: {state}\nTool error: {err}\n\nCommand output:\n{out}");
                assert_eq!(got.as_bytes(),expected.as_bytes());
            }
        }
    }
}

#[test]
fn production_boundary_preserves_unicode_scalar_prefix_and_marker() {
    let arg=input("fixture");
    for scalar in ['x','é','界','🧪'] {
        for length in [11_999,12_000,12_001,13_101] {
            let output=scalar.to_string().repeat(length);
            let (prefix,suffix)=check_parts(&output,12_000);
            assert_eq!(prefix.len(),length.min(12_000)*scalar.len_utf8());
            assert_eq!(suffix,if length>12_000 {SUFFIX} else {""});
            let prompt=pair(&arg,length%4,length%2==0,&tool(&output,Some("unchanged")));
            let displayed=prompt.split_once(OUT_HEADER).unwrap().1;
            assert_eq!(displayed.as_bytes(),[prefix.as_bytes(),suffix.as_bytes()].concat());
        }
    }
}

#[test]
fn zero_and_usize_max_preserve_borrowed_bytes() {
    for value in ["","α","a\u{301}"," 👩‍🔬️ ","\0\n\r"] {
        let (before,rest)=check_parts(value,usize::MAX);
        assert_eq!((before,rest),(value,""));
        let (before,rest)=check_parts(value,0);
        assert_eq!((before,rest),("",if value.is_empty() {""} else {SUFFIX}));
    }
    assert_eq!(check_parts("e\u{301}🧪",1),("e",SUFFIX));
    assert_eq!(check_parts("e\u{301}🧪",2),("e\u{301}",SUFFIX));
}

#[test]
fn generated_prefix_and_full_prompt_controls() {
    let atoms=["é","A","\r","\n","\0","e\u{301}","界","🙂","\u{2028}","👩‍🔬","\n[diagnostics truncated]"];
    let mut seed=182u32;
    let mut next=|n:usize| {
        seed=seed.wrapping_mul(1664525).wrapping_add(1013904223);
        ((seed>>16) as usize)%n
    };
    for i in 0..4096 {
        let mut s=String::new();
        for _ in 0..next(32) { s.push_str(atoms[next(atoms.len())]); }
        let cap=if i%11==0 {usize::MAX} else {next(60)};
        let _=check_parts(&s,cap);
        let request=input(atoms[next(atoms.len())]);
        let error=if i%5==0 {None} else {Some(atoms[next(atoms.len())])};
        let full=pair(&request,i%4,i%2==0,&tool(&s,error));
        assert!(full.ends_with(&s)); // all generated diagnostic texts are below the production limit
    }
}

#[test]
fn suffix_is_appended_without_reinterpreting_existing_marker_or_newlines() {
    let input=input("");
    let src=format!("{}\r{SUFFIX}","a".repeat(11_999));
    let (prefix,mark)=check_parts(&src,12_000);
    assert!(prefix.ends_with('\r'));
    assert_eq!(mark,SUFFIX);
    let actual=pair(&input,0,true,&tool(&src,None));
    assert_eq!(actual.split_once(OUT_HEADER).unwrap().1,format!("{prefix}{mark}"));
    let short=format!("small\r{SUFFIX}");
    let actual=pair(&input,3,false,&tool(&short,Some("")));
    assert_eq!(actual.split_once(OUT_HEADER).unwrap().1,short);
}

#[derive(Clone,Copy,Debug,Default)]
struct Requests {alloc:usize,realloc:usize,bytes:usize}
thread_local! {static METER:Cell<Option<Requests>>=const {Cell::new(None)};}
fn requested(bytes:usize,re:bool) {
    let _=METER.try_with(|meter| {
        if let Some(mut t)=meter.get() {
            t.bytes+=bytes;
            if re {t.realloc+=1;} else {t.alloc+=1;}
            meter.set(Some(t));
        }
    });
}
struct Allocator;
unsafe impl GlobalAlloc for Allocator {
    unsafe fn alloc(&self,a:Layout)->*mut u8 {requested(a.size(),false); unsafe {System.alloc(a)}}
    unsafe fn alloc_zeroed(&self,a:Layout)->*mut u8 {requested(a.size(),false); unsafe {System.alloc_zeroed(a)}}
    unsafe fn realloc(&self,p:*mut u8,a:Layout,n:usize)->*mut u8 {requested(n,true); unsafe {System.realloc(p,a,n)}}
    unsafe fn dealloc(&self,p:*mut u8,a:Layout) {unsafe {System.dealloc(p,a)}}
}
#[global_allocator]
static ALLOCATOR:Allocator=Allocator;
fn measure<T>(body:impl FnOnce()->T)->(T,Requests) {
    assert!(METER.replace(Some(Requests::default())).is_none());
    let value=black_box(body());
    (value,METER.take().unwrap())
}
#[test]
fn scoped_allocations_on_one_production_size_multibyte_output() {
    let request=input("fixture");
    for small in ["","x","α🧪"] {
        let tiny=tool(small,Some("fixture failure"));
        let old=stock::render(&request,0,false,&tiny);
        let new=candidate::render(&request,0,false,&tiny);
        assert_eq!(new.as_bytes(),old.as_bytes());
        assert!(new.capacity()<=old.capacity(), "empty/tiny final capacity");
    }
    let output="🧪".repeat(12_001);
    let result=tool(&output,Some("fixture failure"));
    let (old_flat,old_bound)=measure(|| stock::cap_flat(black_box(&output),12_000));
    let ((prefix,suffix),new_bound)=measure(|| candidate::cap_parts(black_box(&output),12_000));
    assert_eq!(old_flat.as_bytes(),[prefix.as_bytes(),suffix.as_bytes()].concat());
    assert_eq!((new_bound.alloc,new_bound.realloc,new_bound.bytes),(0,0,0));
    assert!(old_bound.alloc>0 && old_bound.bytes>=48_000);
    let (a,old)=measure(|| stock::render(&request,0,false,black_box(&result)));
    let (b,new)=measure(|| candidate::render(&request,0,false,black_box(&result)));
    assert_eq!(a.as_bytes(),b.as_bytes());
    // Requests count the final String too; only the earlier scratch copy is eliminated.
    assert!(old.bytes>new.bytes && b.capacity()<=a.capacity());
    println!("R245_ALLOC {} {} {} {} {} {} {} {} {} {} {} {} {} {}",
        old_bound.alloc,old_bound.realloc,old_bound.bytes,new_bound.alloc,new_bound.realloc,new_bound.bytes,
        old.alloc,old.realloc,old.bytes,new.alloc,new.realloc,new.bytes,a.capacity(),b.capacity());
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
    check(old[:old.index(PROMPT)]==new[:new.index(PROMPT)] and
          section(old,AFTER_PROMPT,TEST_MARK)==section(new,AFTER_PROMPT,TEST_MARK),
          "unchanged workflow and selection/finish code")
    refs={}
    for key,(blob,digest) in REFS.items():
        ref=getattr(args,key).read_bytes()
        identity(ref,blob,digest)
        refs[key]=ref.decode()
    rustc=args.rustc.resolve(strict=True)
    check(hashlib.sha256(rustc.read_bytes()).hexdigest()==RUSTC_SHA,"compiler digest")
    with tempfile.TemporaryDirectory(prefix="r245-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,
                                        text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        unit=root/"lift.rs"
        unit.write_text(TESTS+"\n"+projected_types(refs)+lift("stock",old,False)
                        +lift("candidate",new,True),encoding="utf-8")
        results={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,
                            "-o",exe],check=True,cwd=root,env=env,timeout=90)
            run=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               capture_output=True,text=True,timeout=90)
            check(run.returncode==0,f"{mode} tests:\n{run.stdout}\n{run.stderr}")
            tests=re.search(r"test result: ok\. (\d+) passed; 0 failed;",run.stdout)
            counts=re.search(r"\bR245_ALLOC ((?:\d+ ){13}\d+)$",run.stdout,re.M)
            check(tests is not None and int(tests[1])==12,"test count")
            check(counts is not None,"allocator receipt")
            c=list(map(int,counts[1].split()))
            results[mode]={"tests_passed":int(tests[1]),"generated_pairs":4096,
                           "bound_stock_alloc_realloc_requested_bytes":c[:3],
                           "bound_candidate_alloc_realloc_requested_bytes":c[3:6],
                           "full_prompt_stock_alloc_realloc_requested_bytes":c[6:9],
                           "full_prompt_candidate_alloc_realloc_requested_bytes":c[9:12],
                           "full_prompt_final_capacity_stock_candidate_bytes":c[12:]}
    print(json.dumps({"status":"PASS","rustc":version,"rustc_sha256":RUSTC_SHA,
                      "locked_core":LOCKED_CORE,"exact_forward_and_reverse":True,
                      "production_scalar_limit":12000,"results":results,
                      "actual_project_command_provider_worker_serde_or_cargo":False},indent=2))


if __name__=="__main__":
    main()
