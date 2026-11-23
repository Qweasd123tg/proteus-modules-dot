#!/usr/bin/env python3
"""Verify the exact lazy footer predicate, cutoff, actions and scoped row visits."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

PATH="src/ui/chat/thread.rs"
PINS={
    "stock": ("33afcd0599974f18eef6cd242f43ed2465ce1359", "680bf06e5039454bb168213c3f41eb52b36a18c254aa5c2cc419f3eba2e89639"),
    "candidate": ("a1d766d1aef9aa81be7169976405d1ebf6334889", "7eda3d614f5665ef1a3f90cc7966f5e3ed720a0359ce50ff1ebe74a582e4184f"),
    "patch": ("4cac886eeeee6cd5401798cce436c9d478cee633", "e69750a3d07aba0e2c83c2e63c2e935a400710cbcf52bd571b06c9164b0a12f3"),
    "stamp": ("164355a23cfd49b5f52ed3bea7e2fc9316401d21", "b8b5845df30553c326f8dc3cc75951853c75059c39d3b395bc2db0e4e9348e46"),
    "transcript": ("b2c3333b89aa4d3197c27835c5a6d51fe500b44e", "d6a0e1720e2b588f5afd6ab3ca59ec21bd2913a0ebeed0a1209312156a76f3cf"),
    "prior": ("e8a86db1d83d9b07fbc2926f80ccd5073e03b406", "31ce7c69b1ad9ee042d07422b17151365149966ef36cbe645a683343155860bd"),
}
RUSTC_SHA="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
RUSTC_VERSION="rustc 1.95.0 (59807616e 2026-04-14)"


def check(ok,label):
    if not ok:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def identity(label,b):
    git=hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
    check((git,sha(b))==PINS[label],f"source identity: {label}")


def replay(raw,patch,reverse=False):
    header=(f"diff --git a/{PATH} b/{PATH}\n"
            f"index {PINS['stock'][0]}..{PINS['candidate'][0]} 100644\n"
            f"--- a/{PATH}\n+++ b/{PATH}\n").encode()
    check(patch.startswith(header),"one exact file")
    hunk=patch[len(header):].splitlines(keepends=True)
    check(hunk[0]==b"@@ -145,12 +145,15 @@\n"
          and all(l[:1] in (b" ",b"+",b"-") for l in hunk[1:]),"one exact hunk")
    old,new=([l[1:] for l in hunk[1:] if l[:1]!=k] for k in (b"+",b"-"))
    check((len(old),len(new))==(12,15),"exact hunk lengths")
    if reverse:
        old,new=new,old
    lines=raw.splitlines(keepends=True)
    at=144
    check(lines[at:at+len(old)]==old,"exact hunk context")
    return b"".join(lines[:at]+new+lines[at+len(old):])


def part(s,a,b):
    start=s.index(a)
    return s[start:s.index(b,start+len(a))]


def lift(tag,source):
    code=part(source,"        let end = if !chain_open", "        let image_edge = ")
    check(code.count("self.complete_stamp_tail()")==1, "bind footer completion input")
    code=code.replace("self.complete_stamp_tail()","complete_tail")
    predicate=code[code.index("        let copyable = footer"):]
    check(predicate.count(".iter()")==({"stock":2,"candidate":1}[tag]),"scoped visits instrumentation")
    traced=predicate.replace(".iter()",".iter().inspect(|_| visits.set(visits.get()+1))")
    return (f"mod {tag} {{\nuse super::*;\n"
            + "pub(super) fn projected(entries:&[Entry],ix:usize,chain:Option<Range<usize>>,chain_open:bool,chain_moving:bool,complete_tail:bool)->Projection {\n"
            + code + "Projection{end_key,footer,time,copyable,show:footer && (copyable || time.is_some())}\n}\n"
            + "pub(super) fn decision(turn:&[Entry],footer:bool)->bool {\n"
            + predicate + "copyable\n}\n"
            + "pub(super) fn count(turn:&[Entry],footer:bool)->(bool,usize) {\nlet visits=Cell::new(0);\n"
            + traced + "(copyable,visits.get())\n}\n}\n")


STUB=r'''
use std::{cell::Cell,ops::Range};

#[derive(Clone,Copy,Debug)]
struct Entry {
    role:Role,text:&'static str,key:u64,time:Option<i64>,streaming:bool,hidden:bool,
}
mod stamp {
    use super::*;
    // Opaque decision from the actual subagent progress resolver.
    fn hidden(_: &[Entry],entry:&Entry)->bool {entry.hidden}
/*STAMP*/
}
#[derive(Debug,PartialEq,Eq)]
struct Projection {end_key:u64,footer:bool,time:Option<i64>,copyable:bool,show:bool}
'''

TESTS=r'''
fn entry(role:Role,text:&'static str,key:u64)->Entry {
    Entry{role,text,key,time:None,streaming:false,hidden:false}
}
fn projected(entries:&[Entry],ix:usize,chain:Option<Range<usize>>,chain_open:bool,
             chain_moving:bool,complete_tail:bool)->Projection {
    let a=stock::projected(entries,ix,chain.clone(),chain_open,chain_moving,complete_tail);
    let b=candidate::projected(entries,ix,chain,chain_open,chain_moving,complete_tail);
    assert_eq!(a,b);
    a
}
fn check_decision(entries:&[Entry],footer:bool,expected:bool) {
    assert_eq!(stock::decision(entries,footer),expected);
    assert_eq!(candidate::decision(entries,footer),expected);
}
fn independent(rows:&[Entry],footer:bool)->bool {
    if !footer{return false;}
    let i=rows.iter().rposition(|r|r.role==Role::User);
    match i {
        None=>true,
        Some(i)=>rows[i+1..].iter().any(|r| r.role==Role::Assistant && r.text.chars().any(|c|!c.is_whitespace())),
    }
}

#[test]
fn nearest_user_stops_copy_search_but_userless_loaded_suffix_stays_eligible() {
    let rows=[
        entry(Role::Assistant,"previous answer",10),entry(Role::User,"current",11),
        entry(Role::Assistant,"\t\u{a0}\u{2003}\u{202f}\r\n",12),
        entry(Role::Reasoning,"reasoning text is not an answer",13),
        entry(Role::System,"tool output is not an answer",14),
    ];
    check_decision(&rows,true,false);
    check_decision(&rows[2..],true,true);
    check_decision(&rows[..1],true,true);
    check_decision(&rows[..0],true,true);
    check_decision(&rows,false,false);
    let mut answered=rows;
    answered[2].text="\u{200b}"; // not Unicode whitespace
    check_decision(&answered,true,true);
    let mut answered=rows;
    answered[2].text=" \u{0} ";
    check_decision(&answered,true,true);
}

#[test]
fn exact_end_selection_folded_open_and_moving_with_same_keys_and_time() {
    let mut rows=[
        entry(Role::User,"request",10),entry(Role::Assistant,"reply",11),
        entry(Role::System,"tool1",12),entry(Role::System,"tool2",13),entry(Role::User,"next",14),
    ];
    rows[1].time=Some(99);
    rows[2].time=Some(12); // traversal order, not max time
    let paired=|opened,moving| projected(&rows,2,Some(2..4),opened,moving,false);
    let wanted=Projection{end_key:13,footer:true,time:Some(12),copyable:true,show:true};
    assert_eq!(paired(false,false),wanted);
    assert_eq!(paired(true,true),wanted);
    let open=Projection{end_key:12,footer:false,time:None,copyable:false,show:false};
    assert_eq!(paired(true,false),open);
    assert_eq!(projected(&rows,2,None,false,false,false),open);
}

#[test]
fn no_time_copyable_footer_and_timed_noncopyable_footer_stay_independent() {
    let mut rows=[
        entry(Role::User,"request",20),entry(Role::Assistant," \u{2003} ",21),
        entry(Role::Reasoning,"ignored",22),entry(Role::User,"next",23),
    ];
    rows[2].hidden=true;
    assert_eq!(projected(&rows,1,None,false,false,false),
             Projection{end_key:21,footer:true,time:None,copyable:false,show:false});
    rows[1].time=Some(41);
    assert_eq!(projected(&rows,1,None,false,false,false),
             Projection{end_key:21,footer:true,time:Some(41),copyable:false,show:true});
    rows[1].time=None;
    rows[1].text="answer";
    assert_eq!(projected(&rows,1,None,false,false,false),
             Projection{end_key:21,footer:true,time:None,copyable:true,show:true});
    rows[1].streaming=true;
    assert_eq!(projected(&rows,1,None,false,false,false),
             Projection{end_key:21,footer:false,time:None,copyable:false,show:false});
}

#[test]
fn incomplete_and_loaded_tail_keep_different_footer_decisions() {
    let rows=[entry(Role::Reasoning,"reasoning",30),entry(Role::System,"tool",31)];
    assert_eq!(projected(&rows,1,None,false,false,false),
               Projection{end_key:31,footer:false,time:None,copyable:false,show:false});
    assert_eq!(projected(&rows,1,None,false,false,true),
               Projection{end_key:31,footer:true,time:None,copyable:true,show:true});
}

#[test]
fn all_small_prefixes_and_both_footer_values() {
    let roles=[(Role::User,"has text"),(Role::Assistant,""),(Role::Assistant,"\u{a0}\u{3000}"),
               (Role::Assistant,"é"),(Role::Reasoning,"r"),(Role::System,"tool"),(Role::Assistant," 🧪 ")];
    let mut checked=0;
    for len in 0..=5 {
        for mut code in 0..7_usize.pow(len) {
            let mut rows=Vec::with_capacity(len as usize);
            for i in 0..len {
                let (role,text)=roles[code%roles.len()];
                code/=roles.len();
                rows.push(entry(role,text,i.into()));
            }
            for end in 0..=rows.len() {
                let prefix=&rows[..end];
                for footer in [false,true] {
                    check_decision(prefix,footer,independent(prefix,footer));
                    checked+=1;
                }
            }
        }
    }
    assert_eq!(checked,228_762);
}

#[test]
fn actual_predicate_visits_only_scope_the_eligibility_scan() {
    let count=50_000;
    let mut rows=vec![entry(Role::Assistant,"\u{a0}",1);count];
    assert_eq!(stock::count(&rows,true),(true,2*count));
    assert_eq!(candidate::count(&rows,true),(true,count));
    assert_eq!(stock::count(&rows,false),(false,0));
    assert_eq!(candidate::count(&rows,false),(false,0));
    rows[count-2].role=Role::User;
    let reachable=projected(&rows,count-1,None,false,false,true);
    assert!(reachable.footer && !reachable.copyable);
    assert_eq!(stock::count(&rows,true),(false,count+1));
    assert_eq!(candidate::count(&rows,true),(false,2));
    rows[count-2].role=Role::Assistant;
    rows.last_mut().unwrap().text="answer";
    assert_eq!(stock::count(&rows,true),(true,1));
    assert_eq!(candidate::count(&rows,true),(true,1));
    println!("R252_VISITS 100000 50000 50001 2 1 1 0 0");
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("refs","work","rustc"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args()
    refs={}
    for k in ("stock","stamp","prior","transcript"):
        refs[k]=(args.refs/(k+".ref")).read_bytes()
        identity(k,refs[k])
    patch=Path(__file__).with_name("source.patch").read_bytes()
    identity("patch",patch)
    changed=replay(refs["stock"],patch)
    identity("candidate",changed)
    check(replay(changed,patch,True)==refs["stock"],"exact rollback")
    old=refs["stock"].decode()
    new=changed.decode()
    boundary="        let copyable = footer"
    after="        let image_edge = "
    check(old.split(boundary)[0]==new.split(boundary)[0] and old.split(after)[1]==new.split(after)[1],
          "all code outside copy predicate identical")
    check(".when(footer && (copyable || time.is_some())," in old
          and ".child(self.turn_footer(key, end_key, time, copyable, cx))" in old,
          "exact unchanged action and visibility gate")
    prior=refs["prior"]
    check(b"index 7dc2cce..164355a 100644" in prior and
          b"+        let ending = stamp::turn_end(entries, end, self.complete_stamp_tail());" in prior
          and "        let ending = stamp::turn_end(entries, end, self.complete_stamp_tail());" in old,
          "#403 stamp exact postimage and relocated thread lines")
    role=part(refs["transcript"].decode(),"#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]",
              "#[derive(Clone, Debug)]\npub struct Entry")
    stamp=part(refs["stamp"].decode(),"pub(super) struct TurnEnd","/// The time of row")
    rustc=args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC_SHA,"compiler digest")
    with tempfile.TemporaryDirectory(prefix="r252-",dir=args.work.resolve(strict=True)) as temp:
        root=Path(temp)
        env={"PATH":"/usr/bin:/bin","HOME":temp,"TMPDIR":temp,"LC_ALL":"C"}
        version=subprocess.check_output([rustc,"--version"],cwd=root,env=env,text=True,timeout=20).strip()
        check(version==RUSTC_VERSION,"compiler version")
        unit=root/"lift.rs"
        unit.write_text(role+STUB.replace("/*STAMP*/",stamp)+lift("stock",old)+lift("candidate",new)+TESTS,
                        encoding="utf-8")
        evidence={}
        for mode,flags in [("debug",[]),("optimized",["-O"])]:
            exe=root/("test-"+mode)
            subprocess.run([rustc,"--edition=2024","--test","-Dwarnings",*flags,unit,"-o",exe],
                           cwd=root,env=env,check=True,timeout=90)
            out=subprocess.run([exe,"--test-threads=1","--nocapture"],cwd=root,env=env,
                               text=True,capture_output=True,timeout=90)
            check(out.returncode==0,f"{mode}:\n{out.stdout}\n{out.stderr}")
            check("test result: ok. 6 passed; 0 failed;" in out.stdout,"test count")
            check("R252_VISITS 100000 50000 50001 2 1 1 0 0" in out.stdout,"scoped row visit counts")
            evidence[mode]={"tests":6,"exact_generated_prefix_footer_pairs":228762,
                            "visits_50k_userless_blank_assistant":[100000,50000],
                            "visits_50k_penultimate_user":[50001,2],
                            "visits_latest_answer":[1,1],"visits_no_footer":[0,0]}
    print(json.dumps(dict(status="PASS",rustc=version,rustc_sha256=RUSTC_SHA,exact_apply_reverse=True,
                          pinned_turn_end_with_inert_hidden_input=True,
                          product_ui_run=False,results=evidence),indent=2))


if __name__=="__main__":
    main()
