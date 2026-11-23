#!/usr/bin/env python3
"""Apply/reverse exact SQLite memory sources and test only the pure MATCH operand."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

PATH = "context_provider/sqlite-memory/src/lib.rs"
PINS = {
    "stock": ("99c5f44e60e312222a027c0817c64c35df2d08ad",
              "56f6d4aedfdc1e22a9a801d8368544d52c96bfbdb9b1629867dcf58356737f40"),
    "candidate": ("f536e61f68c47005b35c201a744d3b1296c82af6",
                  "74e9bcfb59817317e28a37728b6ef38c974ef3680f3bb9c0a0e12b6c34c37712"),
    "patch": ("dea8b4b748cd66bf05e13d3fca7be640479d5513",
              "35493132cc96d9527f9be3affa0b1f30dc5d09ff6955322bd4f037692b65b590"),
    "prior": ("a044c16de17f8815c56b02425a1aa8bef8ae0565",
              "af7cffdf52285615119890f87764765f32a1e37dbe12cd497db88ad3969a2c7f"),
}
RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"


def check(ok, label):
    if not ok:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def identity(tag, b):
    git = hashlib.sha1(f"blob {len(b)}\0".encode() + b).hexdigest()
    check((git, sha(b)) == PINS[tag], f"exact identity: {tag}")


def replay(original, patch, reverse=False):
    header = (f"diff --git a/{PATH} b/{PATH}\n"
              f"index {PINS['stock'][0]}..{PINS['candidate'][0]} 100644\n"
              f"--- a/{PATH}\n+++ b/{PATH}\n").encode()
    check(patch.startswith(header), "exact file")
    hunk = patch[len(header):].splitlines(keepends=True)
    check(hunk[0] == b"@@ -177,21 +177,29 @@\n"
          and all(l[:1] in (b" ",b"+",b"-") for l in hunk[1:]), "one hunk")
    old, new = ([l[1:] for l in hunk[1:] if l[:1] != k] for k in (b"+",b"-"))
    check((len(old),len(new)) == (21,29), "exact context line count")
    if reverse:
        old,new=new,old
    lines=original.splitlines(keepends=True)
    at=176
    check(lines[at:at+len(old)]==old,"exact source context")
    return b"".join(lines[:at]+new+lines[at+len(old):])


def split(rust):
    a=rust.index(b"fn fts_match_expression(")
    b=rust.index(b"\npub fn register_modules(",a)
    return rust[:a],rust[a:b],rust[b:]


def lift(tag, code, stock):
    test=stock[stock.index(b"    #[test]\n    fn fts_match_expression_keeps_literal_spans("):]
    check(test.endswith(b"    }\n}\n"),"exact pure embedded test")
    pure_test=test[:-2].decode()
    return "mod "+tag+" {\n"+code.decode().replace("fn fts_match_expression(", "pub(super) fn fts_match_expression(",1)+pure_test+"}\n"


TESTS = r'''
use std::alloc::{GlobalAlloc,Layout,System};
use std::cell::Cell;
use std::hint::black_box;

type Operand=fn(&str)->String;
const BOTH:[Operand;2]=[stock::fts_match_expression,candidate::fts_match_expression];
fn compare(s:&str)->String {
    let before=BOTH[0](s);
    let after=BOTH[1](s);
    assert_eq!(before.as_bytes(),after.as_bytes(),"{s:?}");
    assert!(!after.contains('\0'));
    after
}
fn expected(s:&str,want:&str) {assert_eq!(compare(s),want);}
fn simple_reference(s:&str)->String {
    let mut out=String::new();
    for span in s.split(char::is_whitespace) {
        if !span.chars().any(|c| c.is_alphanumeric() || c=='_' || c=='-') {continue;}
        if !out.is_empty() {out.push_str(" AND ");}
        out.push('"');
        for c in span.chars() {
            match c {
                '\0'=>out.push(' '),
                '"'=>out.push_str("\"\""),
                _=>out.push(c),
            }
        }
        out.push_str("\"*");
    }
    out
}

#[test]
fn eligibility_spans_and_empty_browse_route() {
    for s in [""," \r\n\t\u{2003}\u{1680}","☃ \" \"\" \0 \0\" !!! +/* .",
              "\u{301} \u{200d} 🧪", " \u{3000} * "] {
        expected(s,"");
    }
    expected("☃tag!!! \r\n _ \t - \u{2003}汉٣ \u{202f} Rust",
             "\"☃tag!!!\"* AND \"_\"* AND \"-\"* AND \"汉٣\"* AND \"Rust\"*");
    expected("a\u{200b}b\u{feff}c\u{0085}d",
             "\"a\u{200b}b\u{feff}c\"* AND \"d\"*");
    expected("apple apple! APPLE?","\"apple\"* AND \"apple!\"* AND \"APPLE?\"*");
}

#[test]
fn nul_and_quote_before_inside_after_utf8_and_at_adjacent_boundaries() {
    expected("中\0\"文","\"中 \"\"文\"*");
    expected("\0é\0","\" é \"*");
    expected("\"x\"\"","\"\"\"x\"\"\"\"\"*");
    expected("\"\0\" !\0! \"\0a\"\"\0🧪",
             "\"\"\" a\"\"\"\" 🧪\"*");
    expected("a\0b \0 \"-\" \'_\'",
             "\"a b\"* AND \"\"\"-\"\"\"* AND \"'_'\"*");
}

#[test]
fn all_valid_scalars_in_combination() {
    let all:String=(0..=0x10ffff).filter_map(char::from_u32).collect();
    assert_eq!(all.chars().count(),1_112_064);
    let a=compare(&all);
    assert_eq!(a,simple_reference(&all));
    for b in 0..=127_u8 {
        let t=format!("\0🧪{}\"\0a\u{2003}é\0\"\0",b as char);
        assert_eq!(compare(&t),simple_reference(&t));
    }
}

#[test]
fn exhaustive_small_match_operands() {
    let atoms=["", "a", "é", "३", "β\u{301}", "\u{301}", "🧪", "_", "-", "*", "\"", "\0",
               "\t", "\u{2003}", "\u{0085}", "\u{200b}"];
    let mut count=0;
    for a in atoms {for b in atoms {for c in atoms {for d in atoms {
        let s=format!("{a}{b}{c}{d}");
        assert_eq!(compare(&s),simple_reference(&s));
        count+=1;
    }}}}
    assert_eq!(count,65_536);
}

#[test]
fn many_generated_longer_mixed_spans() {
    let atoms=["い","A7","⚡","\0", "\"\"","é","-","_",":"," + ","\u{202f}","\u{200d}","נ","\u{0085}",
               "Đ","٣","\"\"\0\"","\0\0\0","many-letters","\u{301}"];
    let mut rng=0x43b2_u64;
    for i in 0..4096 {
        let mut s=String::new();
        for _ in 0..i%91 {
            rng=rng.wrapping_mul(6364136223846793005).wrapping_add(1);
            s.push_str(atoms[((rng>>32) as usize)%atoms.len()]);
        }
        assert_eq!(compare(&s),simple_reference(&s));
    }
}

#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Stat {alloc:usize,realloc:usize,bytes:usize}
thread_local!{static METER:Cell<Option<Stat>>=const{Cell::new(None)};}
fn request(n:usize,re:bool) {
    let _=METER.try_with(|m| if let Some(mut s)=m.get(){
        if re{s.realloc+=1;}else{s.alloc+=1;} s.bytes+=n;m.set(Some(s));
    });
}
struct Tracker;
unsafe impl GlobalAlloc for Tracker {
    unsafe fn alloc(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc(l)}}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {request(l.size(),false);unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8 {request(n,true);unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout) {unsafe{System.dealloc(p,l)}}
}
#[global_allocator]
static ALLOCATOR:Tracker=Tracker;
fn measure(operand:Operand,s:&str)->(String,Stat) {
    assert!(METER.replace(Some(Stat::default())).is_none());
    let out=black_box(operand)(black_box(s));
    (out,METER.take().unwrap())
}

#[test]
fn fixed_queries_scope_allocator_to_operand_only() {
    for (label,s) in [("empty"," \u{202f}!!\"\0"),("short","home"),
                      ("ordinary","React Router!!! v6"),
                      ("escaped","\u{2003}Open\"Code\0wrapper Rust-é 需求\t日志 _path") ] {
        let (a,x)=measure(BOTH[0],s);
        let (b,y)=measure(BOTH[1],s);
        assert_eq!(a,b);
        if a.is_empty() {assert_eq!(x,y);assert_eq!(y,Stat::default());}
        else {
            assert!(y.alloc+y.realloc<x.alloc+x.realloc);
            assert!(y.bytes<x.bytes);
        }
        println!("R251_ALLOC {label} {} {} {} {} {} {} {} {}",
                 x.alloc,x.realloc,x.bytes,a.capacity(),y.alloc,y.realloc,y.bytes,b.capacity());
    }
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("refs","rustc","work"):
        p.add_argument("--"+name,type=Path,required=True)
    args=p.parse_args()
    stock=(args.refs/"stock.ref").read_bytes()
    prior=(args.refs/"prior.ref").read_bytes()
    patch=Path(__file__).with_name("source.patch").read_bytes()
    for label,b in (("stock",stock),("prior",prior),("patch",patch)):
        identity(label,b)
    check(b"index 9f9824d..99c5f44 100644\n" in prior
          and b"fn fts_match_expression" not in prior,"#305 already integrated disjoint")
    candidate=replay(stock,patch)
    identity("candidate",candidate)
    check(replay(candidate,patch,True)==stock,"byte rollback")
    oldhead,oldbody,oldtail=split(stock)
    newhead,newbody,newtail=split(candidate)
    check((oldhead,oldtail)==(newhead,newtail),"only exact operand body changed")
    check(b"WHERE memory_fts MATCH ?1" in newhead and
          b"stmt.query_map(params![match_expr, limit], row_to_item)?" in newhead
          and b"if match_expr.is_empty()" in newhead,"intact real read/browse consumers")
    rustc=args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC_SHA,"compiler digest")
    with tempfile.TemporaryDirectory(prefix="r251-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        vers=subprocess.check_output([rustc,"--version"],cwd=root,env=env,text=True,timeout=20).strip()
        check(vers==RUSTC_VERSION,"compiler version")
        unit=root/"lift.rs"
        unit.write_text(lift("stock",oldbody,stock)+lift("candidate",newbody,stock)+TESTS,encoding="utf-8")
        results={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,"-o",exe],
                           check=True,cwd=root,env=env,timeout=90)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               text=True,capture_output=True,timeout=90)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 8 passed; 0 failed;" in out.stdout,"test count")
            rows={}
            for label,receipt in re.findall(r"(?m)\bR251_ALLOC (\w+) ((?:\d+ ){7}\d+)$",out.stdout):
                stats=list(map(int,receipt.split()))
                rows[label]={"stock_alloc_realloc_requested_bytes_capacity":stats[:4],
                             "candidate_alloc_realloc_requested_bytes_capacity":stats[4:]}
            check(set(rows)=={"empty","short","ordinary","escaped"},"all scoped counts")
            results[mode]={"tests_passed":8,"exhaustive_small_cases":65536,"generated_longer_cases":4096,
                           "unicode_scalar_sweep":1112064,"fixture_metrics":rows}
    print(json.dumps(dict(status="PASS",rustc=vers,rustc_sha256=RUSTC_SHA,prior_305_already_integrated=True,
                          exact_apply_reverse_and_unchanged_caller=True,sqlite_executed=False,results=results),indent=2))


if __name__=="__main__":
    main()
