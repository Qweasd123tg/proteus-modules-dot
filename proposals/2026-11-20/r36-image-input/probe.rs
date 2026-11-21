use std::{alloc::{GlobalAlloc, Layout, System}, sync::atomic::{AtomicUsize,Ordering::Relaxed}};
pub use proteus_contracts::{domain, model_standard};
use domain::{ImageAttachment,UserMessageInput};
use model_standard::ContentPart;
mod before;
mod after;

struct Count;
static LIVE:AtomicUsize=AtomicUsize::new(0);
static PEAK:AtomicUsize=AtomicUsize::new(0);
fn add(n:usize){ let new=LIVE.fetch_add(n,Relaxed)+n; PEAK.fetch_max(new,Relaxed); }
fn sub(n:usize){ LIVE.fetch_sub(n,Relaxed); }
unsafe impl GlobalAlloc for Count{
    unsafe fn alloc(&self,l:Layout)->*mut u8{let p=unsafe{System.alloc(l)}; if !p.is_null(){add(l.size())};p}
    unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{let p=unsafe{System.alloc_zeroed(l)};if !p.is_null(){add(l.size())};p}
    unsafe fn dealloc(&self,p:*mut u8,l:Layout){sub(l.size());unsafe{System.dealloc(p,l)}}
    unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{let q=unsafe{System.realloc(p,l,n)};if !q.is_null(){sub(l.size());add(n)};q}
}
#[global_allocator] static A:Count=Count;
fn bytes(n:usize,i:usize)->Vec<u8>{
    let mut b=vec![i as u8;n];b[..8].copy_from_slice(b"\x89PNG\r\n\x1a\n");b
}
fn input(n:usize,s:usize)->UserMessageInput{
    UserMessageInput{text:"caption 🦀".into(),images:(0..n).map(|i|ImageAttachment::from_bytes(format!("изображение{i}.png"),&bytes(s,i)).unwrap()).collect()}
}
fn main(){
    let tmp=tempfile::tempdir().unwrap();
    let old=before::ImageStore::new(tmp.path().to_owned());
    let new=after::ImageStore::new(tmp.path().to_owned());
    println!("case,round,arm,prepared_live_bytes,prepare_peak_live_bytes");
    for (tag,n,len) in [("text",0,0),("tiny",1,64),("one1m",1,1<<20),("one5m",1,5<<20),("four1m",4,1<<20),("four-total5m",4,5<<18)]{
        let mut previous=None;
        for (round,arm) in ["baseline","patch","patch","baseline"].into_iter().enumerate(){
            let base=LIVE.load(Relaxed);
            let input=input(n,len);
            PEAK.store(LIVE.load(Relaxed),Relaxed);
            macro_rules! prepare {($store:path,$admit:ident)=>{
                {let prepared=<$store>::prepare(input).unwrap();
                let live=LIVE.load(Relaxed)-base; let peak=PEAK.load(Relaxed)-base;
                let msg=$admit.admit(prepared).unwrap();(live,peak,msg)}
            }}
            let (live,peak,msg)=if arm=="baseline" {prepare!(before::ImageStore,old)} else {prepare!(after::ImageStore,new)};
            assert_eq!(msg.parts.len(),n+1);
            let mut refs=Vec::new();
            for (i, part) in msg.parts.iter().enumerate(){
                match &part.payload{
                    ContentPart::Image{image}=>{assert!(i<n);assert_eq!(image.name,format!("изображение{i}.png"));assert_eq!(image.mime_type,"image/png");assert_eq!(std::fs::read(&image.path).unwrap(),bytes(len,i));refs.push(image.clone())}
                    ContentPart::Text{text}=>{assert_eq!(i,n);assert_eq!(text,"caption 🦀")}
                    _=>panic!("unexpected content")
                }
            }
            if let Some(ref prev)=previous{assert_eq!(prev,&refs)} else {previous=Some(refs);}
            println!("{tag},{round},{arm},{live},{peak}");
        }
    }
    let mut cases=vec![UserMessageInput::from("   "),UserMessageInput::from("x".repeat(256*1024+1)),input(5,64),input(2,3<<20)];
    let mut invalid=input(2,64);invalid.images[1].data="#".into();cases.push(invalid);
    let mut invalid=input(2,64);invalid.images[1].mime_type="text/plain".into();cases.push(invalid);
    for case in cases{
        let before=before::ImageStore::prepare(case.clone()).err().unwrap();
        let after=after::ImageStore::prepare(case).err().unwrap();assert_eq!(format!("{before:#}"),format!("{after:#}"));
    }
}
