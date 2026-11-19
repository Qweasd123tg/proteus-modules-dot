use gpui::{AppContext as _, TestAppContext, TestDispatcher};
use gpui_base::text::TextViewState;
use serde_json::{json,Value};
use std::collections::BTreeMap;
use std::time::Instant;

// Linux x86_64 process CPU time (includes all threads belonging to this probe).
#[repr(C)]
struct Stamp {sec:i64,nsec:i64}
unsafe extern "C" {fn clock_gettime(id:i32,ts:*mut Stamp)->i32;}
fn cpu()->u64 {let mut t=Stamp{sec:0,nsec:0};assert_eq!(unsafe{clock_gettime(2,&mut t)},0);
    (t.sec as u64)*1_000_000_000+t.nsec as u64}
fn main(){
    let a:Vec<_>=std::env::args().collect();
    let data=std::fs::read_to_string(&a[1]).unwrap();
    let mut bodies:BTreeMap<String,String>=data.lines().map(|s| {
        let v:Value=serde_json::from_str(s).unwrap();(v["name"].as_str().unwrap().into(),v["html"].as_str().unwrap().into())
    }).collect();
    // Same rich 4096-byte input plus a literal ASCII space outside its closing tag.
    bodies.insert("table-4097".into(),bodies["md-table-4096"].clone()+" ");
    bodies.insert("long-53k".into(),"<p>".to_owned()+&"Plain text. ".repeat(4479)+"</p>");
    let mode=&a[2]; let case=&a[3];let src=&bodies[case];let n:usize=a[4].parse().unwrap();let runs:usize=a[5].parse().unwrap();
    let mut cx=TestAppContext::build(TestDispatcher::new(41),Some("deferred_html_tradeoff"));
    let mut rows=Vec::new(); let mut cpu_rows=Vec::new();
    for run in 0..runs+2 {
        let mut states=Vec::with_capacity(n);
        if mode=="append" {
            for _ in 0..n {states.push(cx.new(|cx| TextViewState::html(src,cx)));}
            cx.run_until_parked();
        }
        let t_cpu=cpu();let t=Instant::now();
        if mode=="append" {
            for state in &states {state.update(&mut cx,|v,cx| v.push_str("<p>tail-marker</p>",cx));}
        } else {
            assert_eq!(mode,"init");
            for _ in 0..n {states.push(cx.new(|cx|TextViewState::html(src,cx)));}
        }
        cx.run_until_parked();
        let ns=t.elapsed().as_nanos() as u64;let ns_cpu=cpu()-t_cpu;
        for s in &states {
            s.read_with(&cx,|v,_|{
                assert!(v.is_ready());
                if mode=="append" {assert!(v.rendered_text().as_str().contains("tail-marker"));}
                else {assert!(!v.rendered_text().as_str().trim().is_empty());}
            });
        }
        if run>=2 {rows.push(ns);cpu_rows.push(ns_cpu);}
        drop(states);cx.run_until_parked();
    }
    println!("{}",json!({"mode":mode,"workload":case,"html_bytes":src.len(),"states":n,"samples_ns":rows,"cpu_ns":cpu_rows}));
}
