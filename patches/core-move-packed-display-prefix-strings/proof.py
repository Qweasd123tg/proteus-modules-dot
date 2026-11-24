#!/usr/bin/env python3
"""Verify the cache conversion with real locked Serde and Base64, fully offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

SRC="crates/proteus-core/src/core/session_store/remote/view"
RUSTC_SHA="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
CARGO_SHA="841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66"
MANIFEST='''[package]
name = "r257-prefix-cache-proof"
version = "0.0.0"
edition = "2024"
publish = false

[features]
preserve_order = ["serde_json/preserve_order"]

[dependencies]
base64 = "=0.22.1"
serde = { version = "=1.0.228", features = ["derive"] }
serde_json = "=1.0.151"
'''


def check(value,label):
    if not value:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pin(b,v,label):
    git=hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
    check((git,sha(b))==(v["git_blob"],v["sha256"]),f"identity: {label}")


def part(s,a,b=None):
    i=s.index(a)
    return s[i:] if b is None else s[i:s.index(b,i+len(a))]


def verify_deps(dep,core_lock,metadata):
    lock=(dep/"lockseed"/"Cargo.lock").read_bytes()
    check(sha(lock)==metadata["proof_cargo_lock_sha256"],"isolated proof lock")
    full={(p["name"],p["version"]):p.get("checksum") for p in tomllib.loads(core_lock)["package"]}
    selected=[p for p in tomllib.loads(lock.decode())["package"] if "source" in p]
    check(len(selected)==15,"exact isolated closure")
    for p in selected:
        key=(p["name"],p["version"])
        checksum=p["checksum"]
        base="-".join(key)
        check(p["source"]=="registry+https://github.com/rust-lang/crates.io-index"
              and full.get(key)==checksum,"exact Core lock: "+base)
        check(sha((dep/"archives"/(base+".crate")).read_bytes())==checksum,"official bytes: "+base)
        v=dep/"vendor"/base
        manifest=json.loads((v/".cargo-checksum.json").read_text())
        check(manifest["package"]==checksum,"vendor manifest: "+base)
        for f,expected in manifest["files"].items():
            target=v/f
            check(target.resolve(strict=True).is_relative_to(v.resolve(strict=True)) and
                  not target.is_symlink() and sha(target.read_bytes())==expected,"vendor file: "+base+"/"+f)
    versions={p["name"]:p["version"] for p in selected}
    check(versions["serde_json"]=="1.0.151" and versions["base64"]=="0.22.1"
          and versions["serde"]=="1.0.228" and versions["indexmap"]=="2.14.0","actual lock versions")
    return lock


def apply(root,env,git,refs,meta,patch):
    pin(patch,meta["patch"],"patch")
    conf=env | {"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
                "GIT_CEILING_DIRECTORIES":str(root.parent)}
    repo=root/SRC
    (repo/"prefix").mkdir(parents=True)
    paths={"cache":repo/"cache.rs","packed":repo/"prefix"/"packed.rs"}
    for k,p in paths.items():
        p.write_bytes(refs[k])
    pp=root/"source.patch";pp.write_bytes(patch)
    def step(flags):
        for c in (["--check"],[]):
            subprocess.run([git,"apply",*flags,*c,pp],cwd=root,env=conf,check=True,timeout=20)
    step([])
    result={k:p.read_bytes() for k,p in paths.items()}
    for k,b in result.items():
        pin(b,meta["candidate"][k],k)
    step(["-R"])
    check(all(p.read_bytes()==refs[k] for k,p in paths.items()),"two files revert byte-exact")
    check(result["cache"].replace(b"prefix.encode_cache()?.into_bounded_value()?",b"bounded_value(&prefix.encode_cache()?)?")==refs["cache"],"only prefix write expression changed")
    helper=part(result["packed"].decode(),"impl<C: Serialize> Packed<C>","fn pack<const N: usize>(").encode()
    check(result["packed"].replace(helper,b"")==refs["packed"],"packing and decoder byte-identical")
    return result


def lift(tag, files):
    p=part(files["packed"],"#[derive(Serialize, Deserialize)]","#[cfg(test)]")
    p=p.replace("pub(in crate::core::session_store::remote::view)","pub(super)")
    p=p.replace("crate::core::session_store::json_size::encoded_len","encoded_len")
    c=files["cache"]
    blocks=part(c,"fn hash(value:","fn read_value(")+part(c,"fn write_value(","pub(super) fn read_content")
    blocks+=part(c,"pub(super) fn write_prefix(","pub(super) fn write_content<T:")
    blocks=blocks.replace("crate::core::session_store::json_size::encoded_len","encoded_len")
    blocks=blocks.replace("proteus_contracts::contracts::SESSION_STORAGE_MAX_CACHE_BYTES","LIMIT")
    stmt=part(blocks,"    let value = ","    let digest = ")
    check(stmt.count("prefix.encode_cache()")==1,"actual conversion expression")
    expr=stmt.removeprefix("    let value = ").strip().removesuffix(";").removesuffix("?")
    convert="packed.into_bounded_value()" if "into_bounded_value" in expr else "bounded_value(&packed)"
    return (f"mod {tag} {{\nuse super::*;\n"+p+blocks+
            "pub(super) fn value(prefix:&PrefixIdentities)->Option<Value>{"+expr+"}\n"
            +"fn convert<C:Serialize>(packed:Packed<C>)->Option<Value>{"+convert+"}\n"
            +WRAPPERS+"}\n")


STUB=r'''
#![allow(dead_code)]
use std::{alloc::{GlobalAlloc,Layout,System},cell::{Cell,RefCell},collections::HashSet,hint::black_box};
use serde::{Deserialize,Serialize,Serializer,ser::{SerializeMap,SerializeSeq}};
use serde_json::Value;
use base64::{Engine as _,engine::general_purpose::STANDARD};
type CallId=String;
type TurnId=Uuid;type ExchangeId=Uuid;type MessageId=Uuid;type PartId=Uuid;
#[derive(Clone,Copy,PartialEq,Eq,Hash,Debug,Serialize,Deserialize)]
struct Uuid([u8;16]);
impl Uuid {
    fn from_u128(n:u128)->Self {Self(n.to_be_bytes())}
    fn from_bytes(n:[u8;16])->Self {Self(n)}
    fn from_slice(n:&[u8])->Result<Self,()> {n.try_into().map(Self).map_err(|_|())}
    fn as_bytes(&self)->&[u8;16] {&self.0}
}
#[derive(Debug,Clone,PartialEq,Eq)]
struct Snapshot {session:String,revision:u64,sha:String}
struct RemoteCacheSource {snapshot:Snapshot}
#[derive(Debug,PartialEq)]
enum Request { WriteCache {session:String,key:String,source:Snapshot,value:Value} }
enum Response { CacheWritten {etag:Option<String>}, Other }
struct Descriptor {session:String}
#[derive(Clone,Copy)]
enum Outcome { Ack, Stale, TransportError, Other }
struct RemoteSessionStore {
    descriptor:Descriptor, outcome:Outcome, sent:RefCell<Vec<Request>>,
}
impl RemoteSessionStore {
    fn request(&self,r:Request)->Result<Response,()> {
        self.sent.borrow_mut().push(r);
        match self.outcome {
            Outcome::Ack=>Ok(Response::CacheWritten{etag:Some("stored".into())}),
            Outcome::Stale=>Ok(Response::CacheWritten{etag:None}),
            Outcome::TransportError=>Err(()),
            Outcome::Other=>Ok(Response::Other),
        }
    }
}
thread_local! {
    static HASHES:RefCell<Vec<Vec<u8>>>=const {RefCell::new(Vec::new())};
    static HASH_FAIL:Cell<bool>=const {Cell::new(false)};
}
mod proteus_contracts {
    pub mod contracts {
        // Only the Ring digest / error carrier is inert. The exact OrderedValue
        // implementation still produces the real input bytes to SHA-256.
        pub fn storage_value_etag(v:&serde_json::Value)->Result<String,()> {
            let bytes=serde_json::to_vec(&super::super::OrderedValue(v)).map_err(|_|())?;
            super::super::HASHES.with_borrow_mut(|rows|rows.push(bytes));
            if super::super::HASH_FAIL.get() {Err(())} else {Ok("inert-fingerprint".into())}
        }
    }
}
'''

WRAPPERS=r'''
fn ptrs(p:&Packed<impl Serialize>)->[usize;5] {
    [&p.history,&p.turns,&p.exchanges,&p.messages,&p.parts].map(|s|s.as_ptr() as usize)
}
pub(super) fn allocations(prefix:&PrefixIdentities)->(Value,Stats,[bool;5],usize) {
    let p=prefix.encode_cache().unwrap();
    let from=ptrs(&p);
    let bytes=p.history.len()+p.turns.len()+p.exchanges.len()+p.messages.len()+p.parts.len();
    assert!(METER.replace(Some(Stats::default())).is_none());
    let out=black_box(convert(black_box(p))).unwrap();
    let stats=METER.take().unwrap();
    let fields=["history","turns","exchanges","messages","parts"];
    let remains=std::array::from_fn(|i|out[fields[i]].as_str().unwrap().as_ptr() as usize==from[i]);
    (out,stats,remains,bytes)
}
pub(super) fn refusing_serializer_is_rejected()->bool {
    struct Refuse;
    impl Serialize for Refuse {
        fn serialize<S:Serializer>(&self,_:S)->Result<S::Ok,S::Error> {
            Err(serde::ser::Error::custom("fixture refusal"))
        }
    }
    let p=Packed{format:1,history:"body".into(),turns:String::new(),exchanges:String::new(),
                 messages:String::new(),parts:String::new(),calls:Refuse};
    convert(p).is_none()
}
'''

TESTS=r'''
fn fixture(n:usize)->PrefixIdentities {
    let id=|i:usize|Uuid::from_u128(i as u128+1);
    PrefixIdentities {
        history:(0..n).map(|i|{
            let mut bytes=[0;32];bytes[..16].copy_from_slice(id(i).as_bytes());bytes
        }).collect(),
        turns:(0..n.div_ceil(5)).map(id).collect(),
        exchanges:(0..n.div_ceil(3)).map(id).collect(),
        messages:(0..n).map(id).collect(),
        parts:(0..n).map(id).collect(),
        explicit_committed_parts:(0..n).step_by(2).map(id).collect(),
        calls:HashSet::from([String::new(),"not/UUID: э\n\0🧪".into(),"\"\\quote".into(),"last".into()]),
    }
}
fn matches(a:&PrefixIdentities,b:&PrefixIdentities) {
    assert_eq!(a.history,b.history);
    assert_eq!(a.turns,b.turns);
    assert_eq!(a.exchanges,b.exchanges);
    assert_eq!(a.messages,b.messages);
    assert_eq!(a.parts,b.parts);
    assert_eq!(a.explicit_committed_parts,b.explicit_committed_parts);
    assert_eq!(a.calls,b.calls);
}
fn parity(p:&PrefixIdentities)->Value {
    let old=stock::value(p).unwrap();let new=candidate::value(p).unwrap();
    assert_eq!(old,new);
    assert_eq!(serde_json::to_vec(&old).unwrap(),serde_json::to_vec(&new).unwrap());
    assert_eq!(serde_json::to_vec(&OrderedValue(&old)).unwrap(),serde_json::to_vec(&OrderedValue(&new)).unwrap());
    let keys=new.as_object().unwrap().keys().map(String::as_str).collect::<Vec<_>>();
    if cfg!(feature="preserve_order"){
        assert_eq!(keys,["format","history","turns","exchanges","messages","parts","calls"]);
    } else {
        assert_eq!(keys,["calls","exchanges","format","history","messages","parts","turns"]);
    }
    new
}
#[test]
fn same_input_set_real_map_modes_wire_bytes_order_and_lossless_decode() {
    for p in [PrefixIdentities::default(),fixture(1),fixture(2),fixture(97)] {
        let v=parity(&p);
        let q=stock::PrefixIdentities::decode_cache(v.clone()).unwrap();
        let r=candidate::PrefixIdentities::decode_cache(v.clone()).unwrap();
        matches(&p,&q);matches(&p,&r);
        for (k,width,n) in [
            ("history",32,p.history.len()),("turns",16,p.turns.len()),
            ("messages",16,p.messages.len()),("parts",17,p.parts.len())] {
            let field=v[k].as_str().unwrap();
            assert_eq!(field.len(),base64::encoded_len(width*n,true).unwrap());
            assert_eq!(STANDARD.decode(field).unwrap().len(),width*n);
        }
        assert_eq!(v["calls"],serde_json::to_value(&p.calls).unwrap());
    }
}
#[test]
fn strict_decode_rejects_malformed_base64_and_membership() {
    let p=fixture(2);
    for (key,value) in [
        ("format",serde_json::json!(0)),("turns",serde_json::json!("%%%%")),
        ("calls",serde_json::json!(["x","x"])),("parts",serde_json::json!(STANDARD.encode([9;17]))),
        ("history",serde_json::json!(STANDARD.encode([8;31])))
    ] {
        let mut v=parity(&p);v[key]=value;
        assert!(stock::PrefixIdentities::decode_cache(v.clone()).is_none());
        assert!(candidate::PrefixIdentities::decode_cache(v).is_none());
    }
}

fn stale_scope() -> RemoteCacheSource {
    RemoteCacheSource{snapshot:Snapshot{session:"pinned-session".into(),revision:932,sha:"pinned-hash".into()}}
}
fn run(put:fn(&RemoteSessionStore,&RemoteCacheSource,&PrefixIdentities)->Option<String>,
       p:&PrefixIdentities,outcome:Outcome,hash_fail:bool)->(Option<String>,Vec<Request>,Vec<Vec<u8>>){
    let store=RemoteSessionStore{descriptor:Descriptor{session:"pinned-session".into()},outcome,sent:RefCell::default()};
    HASH_FAIL.set(hash_fail);
    HASHES.with_borrow_mut(Vec::clear);
    let result=put(&store,&stale_scope(),p);
    let hashes=HASHES.with_borrow_mut(std::mem::take);
    (result,store.sent.into_inner(),hashes)
}
#[test]
fn exact_write_prefix_same_request_key_source_hash_input_and_failures() {
    let p=fixture(17);
    let v=parity(&p);
    for (outcome,fail,success) in [
        (Outcome::Ack,false,true),(Outcome::Stale,false,false),(Outcome::TransportError,false,false),
        (Outcome::Other,false,false),(Outcome::Ack,true,false)] {
        let a=run(stock::write_prefix,&p,outcome,fail);
        let b=run(candidate::write_prefix,&p,outcome,fail);
        assert_eq!(a,b);
        assert_eq!(a.0.is_some(),success);
        assert_eq!(a.2,[serde_json::to_vec(&OrderedValue(&v)).unwrap()]);
        if fail {assert!(a.1.is_empty());}
        else {assert_eq!(a.1,[Request::WriteCache{session:"pinned-session".into(),key:PREFIX.into(),
                                          source:stale_scope().snapshot,value:v.clone()}]);}
    }
    let mut p=p;
    p.explicit_committed_parts.insert(Uuid::from_u128(1234567));
    for f in [stock::write_prefix,candidate::write_prefix] {
        assert_eq!(run(f,&p,Outcome::Ack,false),(None,vec![],vec![]));
    }
}
#[test]
fn exact_64_mib_escaped_wire_boundary_and_serialization_rejects_before_writing() {
    assert!(stock::refusing_serializer_is_rejected());
    assert!(candidate::refusing_serializer_is_rejected());
    let mut p=PrefixIdentities::default();
    p.calls.insert(String::new());
    let overhead=serde_json::to_vec(&parity(&p)).unwrap().len();
    // Most bytes are unescaped; 31 quotes add one byte each.
    let mut call="a".repeat(LIMIT-overhead-62);
    call.push_str(&"\"".repeat(31));
    p.calls=HashSet::from([call]);
    for f in [stock::value,candidate::value] {
        let v=f(&p).unwrap();
        assert_eq!(encoded_len(&v,LIMIT),Some(LIMIT));
        assert_eq!(encoded_len(&v,LIMIT-1),None);
    }
    let mut call=p.calls.into_iter().next().unwrap();
    call.push('x');
    p.calls=HashSet::from([call]);
    for f in [stock::write_prefix,candidate::write_prefix] {
        assert_eq!(run(f,&p,Outcome::Ack,false),(None,vec![],vec![]));
    }
}
#[derive(Clone,Copy,Default)]
struct Stats {alloc:usize,realloc:usize,bytes:usize}
thread_local!{static METER:Cell<Option<Stats>>=const{Cell::new(None)};}
fn count(bytes:usize,re:bool){
    let _=METER.try_with(|m| if let Some(mut s)=m.get(){
        if re{s.realloc+=1;}else{s.alloc+=1;}s.bytes+=bytes;m.set(Some(s));
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
#[test]
fn realistic_50k_term_counts_scope_only_packed_conversion() {
    let p=fixture(50_000);
    let (a,x,xp,pre)=stock::allocations(&p);
    let (b,y,yp,post)=candidate::allocations(&p);
    assert_eq!(a,b);
    assert_eq!(serde_json::to_vec(&a).unwrap(),serde_json::to_vec(&b).unwrap());
    assert_eq!(xp,[false;5]);
    assert_eq!(yp,[true;5]);
    assert_eq!(pre,post);
    assert_eq!(x.alloc-y.alloc,5);
    assert_eq!(x.realloc,y.realloc);
    assert_eq!(x.bytes-y.bytes,pre);
    println!("R257_ALLOC {} {} {} {} {} {} {}",x.alloc,x.realloc,x.bytes,y.alloc,y.realloc,y.bytes,pre);
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ("refs","work","rustc","cargo","deps"):
        parser.add_argument("--"+k,type=Path,required=True)
    parser.add_argument("--git",type=Path,default=Path("/usr/bin/git"))
    a=parser.parse_args()
    pkg=Path(__file__).parent
    meta=json.loads((pkg/"SOURCE-PROVENANCE.json").read_text())
    refs={}
    for k,p in meta["reproduction_inputs"].items():
        refs[k]=(a.refs/(k+".ref")).read_bytes()
        pin(refs[k],p,k)
    deps=a.deps.resolve(strict=True)
    lock=verify_deps(deps,refs["lock"].decode(),meta)
    cc=a.cargo.resolve(strict=True);rustc=a.rustc.resolve(strict=True)
    check(sha(cc.read_bytes())==CARGO_SHA and sha(rustc.read_bytes())==RUSTC_SHA,"tools")
    with tempfile.TemporaryDirectory(prefix="r257-",dir=a.work.resolve(strict=True)) as tmp:
        root=Path(tmp);src=root/"src";src.mkdir()
        env={"PATH":"/usr/bin:/bin","HOME":tmp,"TMPDIR":tmp,"LC_ALL":"C",
             "RUSTC":str(rustc),"CARGO_HOME":str(root/"cargo-home"),"CARGO_TARGET_DIR":str(root/"target")}
        changed=apply(root,env,a.git.resolve(strict=True),refs,meta,(pkg/"source.patch").read_bytes())
        (root/"Cargo.toml").write_text(MANIFEST)
        (root/"Cargo.lock").write_bytes(lock)
        text={k:v.decode() for k,v in refs.items()}
        prefix=part(text["prefix"],"#[derive(Debug, Default","impl PrefixIdentities").replace("pub(super) history:","history:")
        limit=re.search(r"pub const SESSION_STORAGE_MAX_CACHE_BYTES: usize = ([^;]+);",text["storage"])[1]
        prefix_key=re.search(r'const PREFIX: &str = ("[^"]+");',text["cache"])[1]
        ordered=part(text["value_hash"],"struct OrderedValue","struct DigestWriter")
        # Alias a shared raw-byte UUID shape; real serialization/base64/size logic are unmodified.
        size=part(text["size"],"use std::io::Write;").replace("pub(super) fn encoded_len","fn encoded_len")
        source=STUB+f"const LIMIT:usize={limit};\nconst PREFIX:&str={prefix_key};\n"+prefix+ordered
        source+="mod size {\n"+size.replace("fn encoded_len","pub(super) fn encoded_len",1)+"}\nuse size::encoded_len;\n"
        source+=lift("stock",text)+lift("candidate",{k:v.decode() for k,v in changed.items()})+TESTS
        # The parent owns PrefixIdentities; both exact impl blocks live in distinct proof modules
        # and need unique method names only to coexist in the synthetic crate.
        for name in ("stock","candidate"):
            start=source.index(f"mod {name} {{")
            end=source.index("\nmod candidate {" if name=="stock" else "\nfn fixture(",start)
            derived=source[start:end]
            derived=derived.replace("fn encode_cache(","fn encode_cache_"+name+"(")
            derived=derived.replace(".encode_cache()",".encode_cache_"+name+"()")
            derived=derived.replace("fn decode_cache(","fn decode_cache_"+name+"(")
            source=source[:start]+derived+source[end:]
            source=source.replace(f"{name}::PrefixIdentities::decode_cache",f"PrefixIdentities::decode_cache_{name}")
        (src/"lib.rs").write_text(source)
        configs=["--offline","--locked","--config",'source.crates-io.replace-with="r257-official-verified"',
                 "--config","source.r257-official-verified.directory="+json.dumps(str(deps/"vendor"))]
        results={}
        for mapname,features in [("default",[]),("preserve_order",["--features","preserve_order"])]:
            for mode,release in [("debug",[]),("optimized",["--release"])]:
                cmd=[cc,"test",*configs,*features,*release,"--lib","--","--test-threads=1","--nocapture"]
                out=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True,timeout=180)
                check(out.returncode==0,f"{mapname}/{mode}:\n{out.stdout}\n{out.stderr}")
                check("test result: ok. 6 passed; 0 failed;" in out.stdout,"test count")
                q=re.search(r"(?m)\bR257_ALLOC ((?:\d+ ){6}\d+)$",out.stdout)
                check(q is not None,"allocation receipt")
                z=list(map(int,q[1].split()))
                results[f"{mapname}/{mode}"]=dict(tests=6,stock_alloc_realloc_requested_bytes=z[:3],
                                                 candidate_alloc_realloc_requested_bytes=z[3:6],
                                                 moved_prefix_bytes=z[6])
                print(f"PASS {mapname}/{mode}",flush=True)
        print(json.dumps(dict(status="PASS",serde_json="1.0.151",base64="0.22.1",real_size_limit=67108864,
                              actual_ring_or_worker_or_full_core=False,results=results),indent=2))


if __name__=="__main__":
    main()
