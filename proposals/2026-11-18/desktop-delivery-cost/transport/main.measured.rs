#![allow(dead_code)]
use anyhow::{ensure,Result};
use std::{path::{Path,PathBuf},io::{self,BufRead},time::Instant};
use serde_json::json;
use sha2::{Digest,Sha256};
mod declarative;
mod preferences;
use proteus_diff as diff;
use declarative::{protocol::{self,Outgoing,Incoming,Content,Server,SurfaceKind},process::{Process,Signal},widget::Node};
fn verify(line:&str)->Result<()> {
    if let Incoming::View{root,..}=protocol::parse(line)? {
        root.visit(&mut |node| assert!(!matches!(node,Node::Unknown),"unknown shipped widget"));
    }
    Ok(())
}
fn main()->Result<()> {
    let a:Vec<_>=std::env::args().collect();
    if a[1]=="--wire" {
        let mut n=0;for l in io::stdin().lock().lines(){verify(&l?)?;n+=1;}
        ensure!(n>=30);println!("{n} wire records parsed; all View nodes recognised");return Ok(());
    }
    let dir=Path::new(&a[1]).canonicalize()?;
    let (catalog,errors)=declarative::manifest::discover(&dir); ensure!(errors.is_empty(),"{errors:?}");
    let e=catalog.iter().find(|e|e.manifest.id=="markdown-render").unwrap();
    let (proc,signals)=Process::spawn(e)?;
    proc.send(&Outgoing::Hello{protocol:protocol::PROTOCOL,features:protocol::FEATURES.iter().map(|x|x.to_string()).collect(),workspace:"/fixture".into(),server:Server{origin:String::new(),token:String::new()}})?;
    let expected=std::fs::read_to_string(&a[2])?;
    let n:usize=a[3].parse()?;
    let mut elapsed=Vec::new();let mut hashes=Vec::new();
    let memory=a.get(4).is_some_and(|v|v=="--memory");
    for i in 0..=n{
        if memory && i==1 {println!("READY");let mut ack=String::new();io::stdin().read_line(&mut ack)?;}
        let rev=Some(i as u64);let text=if i==0 {"warmup".into()}else{format!("{} {}",expected,(i-1)%2)};
        let req=Outgoing::Render{context:"scope".into(),view:"content:0".into(),surface:SurfaceKind::Content,argument:Some("0".into()),session_dir:Some(PathBuf::from("/fixture-session")),content:Some(Content{language:"text/plain".into(),source:text,source_revision:rev,context:json!({"languages":["latex"]})})};
        let t=Instant::now();proc.send(&req)?;
        let data=futures_lite::future::block_on(signals.recv())?;
        let root=data.with_signal(|sig| match sig {
            Signal::Message(Incoming::View{view,source_revision,root,session_dir,..})=>{
                assert_eq!(view,"content:0");assert_eq!(source_revision,rev);assert_eq!(session_dir.as_deref(),Some(Path::new("/fixture-session")));root
            }
            other=>panic!("{other:?}")
        });
        let ns=t.elapsed().as_nanos();
        let Node::RichText{html,inlines,..}=root else {panic!("expected rich text")};
        assert!(inlines.is_empty());if i>0{elapsed.push(ns);hashes.push(format!("{:x}",Sha256::digest(html.as_bytes())));}
    }
    if memory {println!("DONE");let mut ack=String::new();io::stdin().read_line(&mut ack)?;}
    proc.send(&Outgoing::Close{view:"content:0".into()})?;
    println!("{}",json!({"ns":elapsed,"html_sha256":hashes}));
    Ok(())
}
