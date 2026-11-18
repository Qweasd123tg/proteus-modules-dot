extern crate self as proteus_extension;
pub use ::anyhow::{anyhow,Result};
pub use serde_json::{Value,json};
mod value;
pub use value::ValueExt;
mod paths;
mod tree;
use std::cell::Cell;
use tree::{Entry,Kind,Listing,Project};
thread_local! { static CLONES: Cell<usize> = const {Cell::new(0)}; static HIGH: Cell<usize> = const {Cell::new(1)}; }
fn bump(){ CLONES.with(|c| c.set(c.get()+1)); }
fn observe(n:usize){ HIGH.with(|c| c.set(n.max(c.get()))); }

fn main(){
    let mut cases=vec![(32,32,2,0,0),(64,32,2,0,0),(255,0,1,0,0),(256,0,1,0,0),(1,1,40,0,0),(0,0,2,0,0)];
    for a in [1,3,8,16,31] {for b in [2,7,17] {for m in [0,2,3]{for fail in [0,5]{cases.push((a,b,4,m,fail));}}}}
    for (a,b,depth,mix,fail) in cases {
        let mut p=Project::default();let mut reads=vec![];
        CLONES.set(0);HIGH.set(1);
        p.expand_all("project",&mut |folder|{
            reads.push(folder.to_owned());
            let level=folder.matches('/').count();
            if fail>0 && level>0 && folder.rsplit('/').next().unwrap()[1..].parse::<usize>().unwrap()%fail==1{return Err(anyhow!("synthetic missing listing"))}
            let n=if level==0{a}else if level<depth{b}else{0};
            Ok(Listing { entries:(0..n).map(|i| {let name=format!("d{i}");let path=format!("{folder}/{name}");
                Entry {name,path,kind:if mix>0 && i%mix==1{Kind::File}else{Kind::Directory}}}).collect(),truncated:false })
        });
        let mut expanded:Vec<_>=p.expanded.into_iter().collect();expanded.sort();
        println!("{}",json!({"shape":[a,b,depth,mix,fail],"reads":reads,"expanded":expanded,"clones":CLONES.get(),"peak":HIGH.get()}));
    }
}
