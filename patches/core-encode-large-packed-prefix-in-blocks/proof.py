#!/usr/bin/env python3
"""Exact Base64 pack proof: pinned dependency, source parity and paired timing gate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

PATHS={
    "packed":"crates/proteus-core/src/core/session_store/remote/view/prefix/packed.rs",
    "cache":"crates/proteus-core/src/core/session_store/remote/view/cache.rs",
}
RUSTC="bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"
CARGO="841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66"
MANIFEST='''[package]
name = "r259-pack-proof"
version = "0.0.0"
edition = "2024"
publish = false

[dependencies]
base64 = "=0.22.1"
'''


def check(ok,label):
    if not ok:
        raise ValueError(label)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def pin(b,p,k):
    git=hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
    check((git,sha(b))==(p["git_blob"],p["sha256"]),"identity: "+k)


def split(s):
    a=s.index(b"fn pack<const")
    b=s.index(b"\nfn ids(",a)
    return s[:a],s[a:b],s[b:]


def composed(root,env,git,refs,meta,patch):
    pin(patch,meta["patch"],"current patch")
    files={}
    patchpaths=[root/"566.patch",root/"259.patch"]
    patchpaths[0].write_bytes(refs["prior-566"])
    patchpaths[1].write_bytes(patch)
    ec=env | {"GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null",
              "GIT_CEILING_DIRECTORIES":str(root.parent)}
    for k,v in PATHS.items():
        p=root/v;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(refs[k]);files[k]=p
    def read():
        return {k:path.read_bytes() for k,path in files.items()}
    def step(p,rev=False):
        opts=["-R"] if rev else []
        for mode in (["--check"],[]):
            subprocess.run([git,"apply",*opts,*mode,p],cwd=root,env=ec,
                           check=True,timeout=20,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    original=read()
    step(patchpaths[1]);post=read()
    pin(post["packed"],meta["candidate"],"candidate")
    check(post["cache"]==original["cache"],"standalone cache unchanged")
    step(patchpaths[1],True);check(read()==original,"stock reversal")
    previous=None
    for order in (patchpaths,patchpaths[::-1]):
        step(order[0]);mid=read()
        if order[0]==patchpaths[0]: previous=mid
        step(order[1]);merged=read()
        for k,b in merged.items():pin(b,meta["composed"][k],"composed "+k)
        step(order[1],True);check(read()==mid,"composition intermediate reversal")
        step(order[0],True);check(read()==original,"composition stock reversal")
    check(previous is not None,"#566 replay")
    a,b,c=split(original["packed"]);x,y,z=split(post["packed"])
    p,q,r=split(previous["packed"]);m,n,o=split(merged["packed"])
    check(a==x and c==z and b==q and y==n and p==m and r==o,
          "only helper body changes in stock and #566 tiers")
    check(previous["cache"]==merged["cache"],"preflight and #566 write byte-identical")
    return b,y


def verify_base64(deps,refs,meta):
    version="base64-0.22.1"
    archive=deps/"archives"/(version+".crate")
    checksum=sha(archive.read_bytes())
    arr=tomllib.loads(refs["lock"].decode())["package"]
    ref=next(p for p in arr if p["name"]=="base64" and p["version"]=="0.22.1")
    check(checksum==ref["checksum"]==meta["base64_archive_sha256"],"official lock-matched base64 archive")
    vendor=deps/"vendor"/version
    sums=json.loads((vendor/".cargo-checksum.json").read_text())
    check(sums["package"]==checksum,"vendor archive checksum")
    for rel,digest in sums["files"].items():
        f=vendor/rel
        check(f.resolve(strict=True).is_relative_to(vendor.resolve(strict=True)) and not f.is_symlink()
              and sha(f.read_bytes())==digest,"vendor file "+rel)
    lock=meta["isolated_cargo_lock_text"].encode()
    check(sha(lock)==meta["isolated_cargo_lock_sha256"],"proof lock")
    packages=[p for p in tomllib.loads(lock.decode())["package"] if "source" in p]
    check(len(packages)==1 and packages[0]["checksum"]==checksum,"exact proof dependency")
    return lock


TESTS=r'''
#[cfg(test)]
mod tests {
    use crate::{stock,selected};
    use base64::{Engine as _,engine::general_purpose::STANDARD};
    use std::{alloc::{GlobalAlloc,Layout,System},cell::Cell,hint::black_box};

    fn records<const N:usize>(count:usize)->Vec<[u8;N]> {
        let mut seed=9428u64;
        (0..count).map(|_|std::array::from_fn(|_|{
            seed=seed.wrapping_mul(6364136223846793005).wrapping_add(1);
            (seed>>32) as u8
        })).collect()
    }
    fn pair<const N:usize>(data:&[[u8;N]],hint:usize) {
        let a=stock::pack(data.iter().copied(),hint);
        let b=selected::pack(data.iter().copied(),hint);
        assert_eq!(a.as_bytes(),b.as_bytes());
        assert_eq!(STANDARD.decode(b).unwrap(),data.as_flattened());
    }
    #[test]
    fn exact_boundaries_padding_and_size_hint_at_all_real_widths() {
        fn edges<const N:usize>() {
            for n in [0,1,2,3,23,24,25,44,45,46,47,48,49,50,51,94,95,96,97,98,144,150,50_000] {
                let r=records::<N>(n);
                for hint in [0,n,n.saturating_sub(1),n+3,49,97] {pair(&r,hint);}
            }
        }
        edges::<16>();edges::<17>();edges::<32>();
    }
    #[test]
    fn generated_ordered_records_match_canonical_reverse_decode() {
        fn test<const N:usize>() {
            let data=records::<N>(1400);
            for i in 0..1134 {
                let len=(i*397)% (data.len()-1);
                let skip=i%(data.len()-len);
                pair(&data[skip..skip+len],(i*811)%1600);
            }
        }
        test::<16>();test::<17>();test::<32>();
    }
    #[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
    struct Stats {alloc:usize,realloc:usize,bytes:usize}
    thread_local!{static METER:Cell<Option<Stats>>=const{Cell::new(None)};}
    fn count(n:usize,re:bool){
        let _=METER.try_with(|m|if let Some(mut x)=m.get(){
            if re{x.realloc+=1;}else{x.alloc+=1;}x.bytes+=n;m.set(Some(x));
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
    fn measured(f:impl FnOnce()->String)->(String,Stats) {
        assert!(METER.replace(Some(Stats::default())).is_none());
        let s=black_box(f());
        (s,METER.take().unwrap())
    }
    #[test]
    fn large_reuses_one_final_allocation_and_small_traffic_is_identical() {
        fn allocs<const N:usize>() {
            for n in [0,1,47,48,49,50_000] {
                let r=records::<N>(n);
                let (a,x)=measured(||stock::pack(black_box(r.iter().copied()),n));
                let (b,y)=measured(||selected::pack(black_box(r.iter().copied()),n));
                assert_eq!(a,b);
                if n<=48 {assert_eq!(x,y);}
                else {
                    assert_eq!((x.alloc,y.alloc,x.realloc,y.realloc),(2,1,0,0));
                    assert_eq!(x.bytes-y.bytes,n*N);
                    assert_eq!(b.capacity(),a.capacity());
                    if n==50_000 {
                        println!("R259_ALLOC {N} {} {} {} {} {} {}",x.alloc,x.realloc,x.bytes,y.alloc,y.realloc,y.bytes);
                    }
                }
            }
        }
        allocs::<16>();allocs::<17>();allocs::<32>();
    }
}
'''


PERF=r'''
use std::{hint::black_box,time::Instant};
mod stock;
mod selected;
const PAIRS:usize=49;
fn input<const N:usize>(n:usize)->Vec<[u8;N]>{
    let mut x=1234567u64;
    (0..n).map(|_|std::array::from_fn(|_|{x=x.wrapping_mul(6364136223846793005).wrapping_add(1);(x>>32)as u8})).collect()
}
#[inline(never)]
fn run<const NEW:bool,const N:usize>(rows:&[[u8;N]])->String {
    if NEW {selected::pack(rows.iter().copied(),rows.len())}
    else {stock::pack(rows.iter().copied(),rows.len())}
}
#[repr(C)]
struct Timespec { sec:std::ffi::c_long, ns:std::ffi::c_long }
unsafe extern "C" { fn clock_gettime(clock:std::ffi::c_int,stamp:*mut Timespec)->std::ffi::c_int; }
fn process_ns()->u64 {
    let mut ts=Timespec{sec:0,ns:0};
    // Linux CLOCK_PROCESS_CPUTIME_ID; this private benchmark is single-threaded.
    assert_eq!(unsafe{clock_gettime(2,&mut ts)},0);
    ts.sec as u64*1_000_000_000+ts.ns as u64
}
fn times(f:impl Fn(),r:usize)->[f64;2] {
    let start=Instant::now();
    let cpu=process_ns();
    for _ in 0..r { f(); }
    let cpu_used=process_ns()-cpu;
    [start.elapsed().as_nanos() as f64/r as f64,cpu_used as f64/r as f64]
}
fn sample(label:&str,kind:&str,stock:&mut Vec<f64>,new:&mut Vec<f64>,ratios:&mut Vec<f64>,ab:&mut Vec<f64>,ba:&mut Vec<f64>){
    for t in [&mut *stock,&mut *new,&mut *ratios,&mut *ab,&mut *ba] { t.sort_by(f64::total_cmp); }
    println!("R259_PERF {label}/{kind} {:.2} {:.2} {:.4} {:.4} {:.4} {:.4} {:.4} {} {}",
             stock[PAIRS/2],new[PAIRS/2],ratios[4],ratios[PAIRS/2],ratios[44],
             ab[ab.len()/2],ba[ba.len()/2],ab.len(),ba.len());
}
fn report(label:&str,short_r:usize,old:impl Fn(),new:impl Fn()){
    let r=short_r*3;
    for _ in 0..4 { black_box(times(&old,r));black_box(times(&new,r)); }
    let make=||[Vec::<f64>::new(),Vec::new()];
    let mut a=make();let mut b=make();let mut r_all=make();let mut ab=make();let mut ba=make();
    let mut rng=7393153u64;
    for i in 0..PAIRS {
        rng=rng.wrapping_mul(6364136223846793005).wrapping_add(1);
        let old_first=((rng>>32) as usize+i)%2==0;
        let (x,y)=if old_first {(times(&old,r),times(&new,r))}
                  else {let y=times(&new,r);(times(&old,r),y)};
        for k in 0..2 {
            a[k].push(x[k]);b[k].push(y[k]);
            let v=y[k]/x[k];r_all[k].push(v);
            if old_first{ab[k].push(v)}else{ba[k].push(v)}
        }
    }
    for (k,kind) in ["wall","cpu"].iter().enumerate(){
        sample(label,kind,&mut a[k],&mut b[k],&mut r_all[k],&mut ab[k],&mut ba[k]);
    }
}
fn simple<const N:usize>(n:usize,r:usize){
    let rows=input::<N>(n);
    assert_eq!(run::<false,N>(&rows),run::<true,N>(&rows));
    report(&format!("w{N}/n{n}"),r,
           ||{black_box(run::<false,N>(black_box(&rows)));},
           ||{black_box(run::<true,N>(black_box(&rows)));});
}
fn cohort<const N:usize>(sizes:&[usize],r:usize){
    let rows=sizes.iter().map(|n|input::<N>(*n)).collect::<Vec<_>>();
    for m in &rows {assert_eq!(run::<false,N>(m),run::<true,N>(m));}
    report(&format!("w{N}/small"),r,
           ||{for m in &rows {black_box(run::<false,N>(black_box(m)));}},
           ||{for m in &rows {black_box(run::<true,N>(black_box(m)));}});
}
fn mixed(){
    let h=input::<32>(50_000);let t=input::<16>(10_000);let x=input::<16>(16_667);
    let m=input::<16>(50_000);let p=input::<17>(50_000);
    fn all<const NEW:bool>(h:&[[u8;32]],t:&[[u8;16]],x:&[[u8;16]],m:&[[u8;16]],p:&[[u8;17]]){
        black_box(run::<NEW,32>(black_box(h)));black_box(run::<NEW,16>(black_box(t)));
        black_box(run::<NEW,16>(black_box(x)));black_box(run::<NEW,16>(black_box(m)));
        black_box(run::<NEW,17>(black_box(p)));
    }
    report("mixed50k",4,||all::<false>(&h,&t,&x,&m,&p),||all::<true>(&h,&t,&x,&m,&p));
}
fn main(){
    let sizes=[1,2,3,8,16,32];
    cohort::<16>(&sizes,8192);cohort::<17>(&sizes,8192);cohort::<32>(&sizes,8192);
    for (n,reps) in [(47,8192),(48,8192),(49,8192),(128,4096),(512,1024),(50_000,12)]{
        simple::<16>(n,reps);simple::<17>(n,reps);simple::<32>(n,reps);
    }
    mixed();
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("refs","work","rustc","cargo","deps"):
        p.add_argument("--"+key,type=Path,required=True)
    p.add_argument("--git",type=Path,default=Path("/usr/bin/git"))
    p.add_argument("--taskset",type=Path,default=Path("/usr/bin/taskset"))
    p.add_argument("--cpu",type=int)
    a=p.parse_args()
    pkg=Path(__file__).parent
    meta=json.loads((pkg/"SOURCE-PROVENANCE.json").read_text())
    refs={}
    for k,i in meta["inputs"].items():
        b=(a.refs/(k+".ref")).read_bytes();pin(b,i,k);refs[k]=b
    deps=a.deps.resolve(strict=True);lock=verify_base64(deps,refs,meta)
    rustc=a.rustc.resolve(strict=True);cargo=a.cargo.resolve(strict=True)
    check(sha(rustc.read_bytes())==RUSTC and sha(cargo.read_bytes())==CARGO,"exact compiler")
    available=os.sched_getaffinity(0)
    cpu=min(available) if a.cpu is None else a.cpu
    check(cpu in available,"CPU availability")
    with tempfile.TemporaryDirectory(prefix="r259-",dir=a.work.resolve(strict=True)) as tmp:
        root=Path(tmp)
        env={"PATH":"/usr/bin:/bin","HOME":tmp,"TMPDIR":tmp,"LC_ALL":"C","RUSTC":str(rustc),
             "CARGO_HOME":str(root/"cargo-home"),"CARGO_TARGET_DIR":str(root/"target")}
        before,after=composed(root,env,a.git.resolve(strict=True),refs,meta,(pkg/"source.patch").read_bytes())
        (root/"Cargo.toml").write_text(MANIFEST);(root/"Cargo.lock").write_bytes(lock)
        src=root/"src";src.mkdir()
        for name,code in [("stock",before),("selected",after)]:
            (src/(name+".rs")).write_text("use base64::{Engine as _,engine::general_purpose::STANDARD};\n"+
                    code.decode().replace("fn pack<","pub fn pack<",1))
        (src/"lib.rs").write_text("mod stock; mod selected;"+TESTS)
        (src/"main.rs").write_text(PERF)
        flags=["--offline","--locked","--config",'source.crates-io.replace-with="r259-official-verified"',
               "--config","source.r259-official-verified.directory="+json.dumps(str(deps/"vendor"))]
        results={}
        for mode,prof in [("debug",[]),("optimized",["--release"])]:
            result=subprocess.run([cargo,"test",*flags,*prof,"--lib","--","--test-threads=1","--nocapture"],
                                  cwd=root,env=env,capture_output=True,text=True,timeout=90)
            check(result.returncode==0,f"{mode}:\n{result.stdout}\n{result.stderr}")
            check("test result: ok. 3 passed; 0 failed;" in result.stdout,"exact test count")
            data={int(k):list(map(int,v.split())) for k,v in re.findall(r"(?m)\bR259_ALLOC (\d+) ((?:\d+ ){5}\d+)$",result.stdout)}
            check(set(data)=={16,17,32},"row widths measured")
            results[mode]=dict(tests_passed=3,generated_cases=3402,allocations_50k=data)
        build=subprocess.run([cargo,"build",*flags,"--release","--bin","r259-pack-proof"],cwd=root,env=env,
                            capture_output=True,text=True,timeout=90)
        check(build.returncode==0,build.stderr)
        cmd=[a.taskset.resolve(strict=True),"-c",str(cpu),root/"target/release/r259-pack-proof"]
        throughput={}
        blocked=[]
        for round_ in range(2):
            run=subprocess.run(cmd,cwd=root,env=env,check=True,capture_output=True,text=True,timeout=150)
            rows={}
            for key,x,y,p10,median,p90,ab,ba,an,bn in re.findall(
                    r"(?m)^R259_PERF (\S+)"+r" ([0-9.]+)"*7+r" (\d+) (\d+)$",run.stdout):
                rows[key]=dict(stock_median_ns=float(x),candidate_median_ns=float(y),
                             ratio_p10=float(p10),ratio_median=float(median),ratio_p90=float(p90),
                             stock_first_median_ratio=float(ab),candidate_first_median_ratio=float(ba),
                             stock_first_pairs=int(an),candidate_first_pairs=int(bn))
            check(len(rows)==44,"all 22 warmed paired cohorts on both clocks")
            for key,m in rows.items():
                if (m["ratio_median"]>1.10 or m["ratio_p90"]>1.25 or
                        max(m["stock_first_median_ratio"],m["candidate_first_median_ratio"])>1.15):
                    blocked.append(dict(round=round_+1,cohort=key,measurements=m))
            throughput[str(round_+1)]=rows
            print(f"measured round {round_+1}, both clocks",flush=True)
        report=dict(status="HOLD" if blocked else "PASS",exact_both_order_566=True,base64="0.22.1",
                    tested_cpu=cpu,pairs_per_cohort=49,warmup_pairs=4,window_repeat_multiplier=3,
                    acceptance={"max_median_ratio":1.10,"max_p90_ratio":1.25,"max_order_split_median_ratio":1.15},
                    throughput=throughput,blocked=blocked,results=results,native_core_or_rss=False)
        print(json.dumps(report,indent=2))
        if blocked:
            raise SystemExit(2)


if __name__=="__main__":
    main()
