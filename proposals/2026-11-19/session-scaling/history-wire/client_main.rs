#![allow(dead_code)]
mod api;
mod startup_trace;
use api::Api;
use proteus_contracts::app_protocol::{AppTranscriptCursor,AppTranscriptPage};
fn check(page:&AppTranscriptPage,n:usize,before:usize,rev:&str){
    assert_eq!((page.total,page.start,page.messages.len(),page.revision.as_str()),(n,before-50,50,rev));
    for (i,m) in page.messages.iter().enumerate(){assert_eq!(m.text,format!("page {}: synthetic café {}",i+page.start,"q".repeat(64)));}
}
fn main() {
    let args:Vec<String>=std::env::args().collect(); let dir=std::path::Path::new(&args[2]);let n:usize=args[3].parse().unwrap(); let rev=&args[4];
    let client=Api::new(&args[1],"session-secret");
    let reps:usize=std::env::var("PERF6_REPS").unwrap_or("3".into()).parse().unwrap();
    for rep in 0..=reps { for (label,before,known) in [("head",n,false),("tail",n,true),("middle",n/2,true),("oldest",50,true)] {
        let c=AppTranscriptCursor{revision:rev.clone(),before,base:None};
        let start=std::time::Instant::now(); let page=if known{client.history_page(dir,&c)}else{client.initial_history_page(dir)}.unwrap(); let ns=start.elapsed().as_nanos();
        check(&page,n,before,rev); println!("CLIENT n={n} rep={rep} pos={label} ns={ns}");
    }}
    if std::env::var_os("PERF6_SKIP_SWEEP").is_none(){
    let mut pos=n; let mut ns=0; while pos>0 {
         let c=AppTranscriptCursor{revision:rev.clone(),before:pos,base:None};
         let start=std::time::Instant::now();let page=client.history_page(dir,&c).unwrap();ns+=start.elapsed().as_nanos();check(&page,n,pos,rev);pos=page.start;
    } println!("C_SWEEP n={n} ns={ns}");}
}
