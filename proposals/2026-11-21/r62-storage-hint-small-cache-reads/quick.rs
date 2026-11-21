use std::{
    alloc::{GlobalAlloc, Layout, System},
    cell::Cell,
    fs::{self, File},
    io::{self, Read},
    path::{Path, PathBuf},
};
struct Counter;
#[global_allocator]
static ALLOC: Counter = Counter;
thread_local! { static METER: Cell<Option<(u64,u64)>> = const { Cell::new(None) }; }
fn track(bytes: usize) {
    METER.with(|cell| if let Some((n,b))=cell.get() {cell.set(Some((n+1,b+bytes as u64)));});
}
unsafe impl GlobalAlloc for Counter {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 { track(l.size()); unsafe { System.alloc(l) } }
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8 {track(l.size());unsafe{System.alloc_zeroed(l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{track(n); unsafe{System.realloc(p,l,n)}}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){unsafe{System.dealloc(p,l)}}
}
const READ_LIMIT: usize = 65*1024*1024;
const CAP: usize = 64*1024;
fn read_known_size(file: File, disk_size:u64, maximum:usize, condition:u8)->(bool,Vec<u8>,u64,u64) {
    let hint=match condition {
        0=>0,
        1=>disk_size.min(CAP.min(maximum) as u64) as usize,
        2 if disk_size<=CAP.min(maximum) as u64=>disk_size as usize,
        2=>0,
        _=>unreachable!(),
    };
    METER.set(Some((0,0)));
    let mut bytes=Vec::with_capacity(hint);
    let read = file.take(maximum as u64+1).read_to_end(&mut bytes);
    let (n,total)=METER.replace(None).unwrap();
    (read.is_ok() && bytes.len()<=maximum,bytes,n,total)
}
fn fetch(path:&Path,condition:u8)->(Vec<u8>,u64,u64) {
    let file=File::open(path).unwrap();
    let info=file.metadata().unwrap();
    assert!(info.is_file());
    let (ok,bytes,n,total)=read_known_size(file,info.len(),READ_LIMIT,condition);
    assert!(ok);
    (bytes,n,total)
}
fn control(dir:&Path) -> io::Result<()> {
    let absent=dir.join("absent"); assert!(File::open(&absent).is_err() && !absent.exists());
    let directory=dir.join("directory"); fs::create_dir(&directory)?;
    assert!(!File::open(&directory)?.metadata()?.is_file());
    println!("missing and non-regular controls fail before buffer allocation");
    let p=dir.join("record");
    for (label,bytes,limit) in [
        ("empty",0,READ_LIMIT),("tiny",3,READ_LIMIT),("small",256,READ_LIMIT),
        ("limit-exact",4096,4096),("limit-short",4097,4096),
        ("large",80*1024,READ_LIMIT),("zero-limit",2,0)
    ] {
        fs::write(&p,vec![b'x';bytes])?;
        let mut expected=None;
        for condition in [0,1,2] {
            let file=File::open(&p)?;
            let n=file.metadata()?.len();
            let (ok,v,calls,alloc)=read_known_size(file,n,limit,condition);
            assert_eq!((ok,v.len()),(bytes<=limit,bytes.min(limit+1)));
            assert!(v.iter().all(|&b|b==b'x'));
            let observed=(ok,v.len(),v.capacity(),calls,alloc);
            if expected.is_none() { expected=Some(observed); }
            if label=="empty" { assert_eq!(Some(observed),expected); }
            println!("control {label} mode={condition} ok={} read={} capacity={} calls={} requested={}",
                     observed.0,observed.1,observed.2,observed.3,observed.4);
        }
    }
    for kept in [0,1024] {
        for condition in [0,1,2] {
            fs::write(&p,vec![b'x';CAP])?;
            let file=File::open(&p)?;
            let old_size=file.metadata()?.len();
            std::fs::OpenOptions::new().write(true).open(&p)?.set_len(kept)?;
            let (ok,v,calls,alloc)=read_known_size(file,old_size,READ_LIMIT,condition);
            assert!(ok && v.len()==kept as usize && v.iter().all(|&b|b==b'x'));
            println!("owned shrink 65536->{kept} mode={condition} capacity={}, calls={calls}, requested={alloc}",v.capacity());
        }
    }
    for condition in [0,1,2] {
        let replace=dir.join("replace");
        fs::write(&p,b"source bytes")?;
        let file=File::open(&p)?;
        let old_size=file.metadata()?.len();
        fs::write(&replace,b"new generation")?;
        fs::rename(replace,&p)?;
        let (ok,v,_,_)=read_known_size(file,old_size,READ_LIMIT,condition);
        assert!(ok && &v==b"source bytes");
    }
    println!("ordinary replacement reads the old open object in every mode");
    Ok(())
}
fn io_count()->(u64,u64) {
    let text=fs::read_to_string("/proc/self/io").unwrap();
    let get=|key:&str|text.lines().find_map(|l|l.strip_prefix(key)).unwrap().trim().parse().unwrap();
    (get("syscr:"),get("rchar:"))
}
fn main()->io::Result<()> {
    let dir=PathBuf::from(std::env::args_os().nth(1).unwrap());
    if let Some(s) = std::env::args_os().nth(2) {
        control(&PathBuf::from(s))?;
    }
    let mut p:Vec<_>=fs::read_dir(dir)?.map(|e|e.unwrap()).filter(|entry|{
        let name=entry.file_name();
        let name=name.to_string_lossy();
        name.starts_with(".storage-cache-")&&name.ends_with(".json")
    }).map(|entry|entry.path()).collect();
    p.sort();
    let mut total=0;
    for path in &p {
        let (a,_,_)=fetch(path,0);
        let (b,_,_)=fetch(path,1);
        assert_eq!(a,b);
        assert_eq!(a,fetch(path,2).0);
        total+=a.len();
    }
    println!("files {:.0} data_bytes {total}", p.len());
    for cap in [0,1,2,2,1,0] {
        let before=io_count();
        let (mut calls,mut req,mut capacity)=(0,0,0);
        for path in &p {
            let (v,n,sum)=fetch(path,cap);
            calls+=n; req+=sum; capacity+=v.capacity();
            std::hint::black_box(v);
        }
        let after=io_count();
        println!("hint_mode {cap}: calls {calls}, requests {req}, final_capacity {capacity}, syscr_delta {}, rchar_delta {}",
                 after.0-before.0,after.1-before.1);
    }
    Ok(())
}
