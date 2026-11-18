extern crate self as proteus_extension;
use std::io::{self,Read};
use serde_json::{Value,json};
mod ui {pub fn svg(_: &str,_:f64,_:f64)->serde_json::Value{unreachable!("only JSON tables exercised")}}
mod catalog;mod fences;mod references;
fn main(){
 let mut input=String::new();io::stdin().read_to_string(&mut input).unwrap();
 let params:Value=serde_json::from_str(&input).unwrap();
 let text=params["text"].as_str().unwrap();
 if params["mode"]=="gfm"{
  let h=markdown::to_html_with_options(text,&markdown::Options::gfm()).unwrap();println!("{}",json!({"html":h}));return
 }
 let allowed=if params["registered"]==true{vec!["json-render".to_owned()]}else{vec![]};
 let f=fences::parse(text,&allowed).blocks.into_iter().next().unwrap();
 if !f.claimed{println!("{}",json!({"claimed":false,"closed":f.closed,"language":f.language}));return}
 match catalog::render(&f.language,&f.code){
 Ok(v)=>println!("{}",json!({"claimed":true,"closed":f.closed,"tree":v})),
 Err(e)=>println!("{}",json!({"claimed":true,"error":format!("{e:#}")})),
 }
}
