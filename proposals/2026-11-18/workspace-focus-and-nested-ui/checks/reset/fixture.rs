use serde_json::{json,Map,Value};
use std::collections::BTreeMap;
#[derive(Default,Clone)] struct Draft{config:BTreeMap<String,BTreeMap<String,Value>>}
#[derive(Clone)]struct FieldPath{slot:String,module:String,keys:Vec<String>}
impl Draft{/* METHODS */}
/* HELPERS */
fn draft(value:Value)->Draft{let mut d=Draft::default();d.config.entry("ui".into()).or_default().insert("theme".into(),value);d}
fn path(keys:&[&str])->FieldPath{FieldPath{slot:"ui".into(),module:"theme".into(),keys:keys.iter().map(|&x|x.into()).collect()}}
fn erase(d:&mut Draft,p:&FieldPath,b:&Draft){/* RESET */}
fn val(d:&Draft)->Value{d.module_config("ui","theme").unwrap().clone()}
fn main(){
 let mut count=0;let mut errs=vec![];
 for (title,original,make,leaf,expected) in [
  ("nested empty",json!({"page":{"filters":{}}}),Some(json!(false)),vec!["page","filters","draft","sort"],json!({"page":{"filters":{}}})),
  ("empty grandparent",json!({"page":{}}),Some(json!("draft")),vec!["page","new","label"],json!({"page":{}})),
  ("explicit baseline = default",json!({"page":{"enabled":true}}),None,vec!["page","enabled"],json!({})),
  ("explicit saved nondefault",json!({"page":{"enabled":false}}),None,vec!["page","enabled"],json!({})),
  ("empty field itself",json!({"page":{"empty":{}}}),None,vec!["page","empty"],json!({})),
  ("exact group target wiped",json!({"a":{"g":{"saved":false}},"s":{"q":1}}),None,vec!["a","g"],json!({"s":{"q":1}})),
  ("omitted ancestors",json!({}),Some(json!("new")),vec!["a","b","c"],json!({})),
  ("preserve scalar sibling",json!({"a":{"s":"hello"}}),Some(json!("new")),vec!["a","b","c"],json!({"a":{"s":"hello"}})),
  ("preserve nonempty container",json!({"a":{"k":[]}}),Some(json!("new")),vec!["a","b","c"],json!({"a":{"k":[]}})),
  ("two saved empty",json!({"a":{"b":{},"c":{}}}),Some(json!(null)),vec!["a","b","new"],json!({"a":{"b":{},"c":{}}})),
 ]{
   let b=draft(original.clone()); let mut d=b.clone(); let p=path(&leaf);
   if let Some(x)=make { d.set_value(&p,Some(x));}
   d.set_value(&path(&["other","draft"]),Some(json!("keep")));
   let mut expected=expected; expected["other"]=json!({"draft":"keep"});
   erase(&mut d,&p,&b);
   count+=1; if val(&d)!=expected {errs.push(title)};
   assert_eq!(val(&b),original);
 }
 println!("{count} scenarios; failures={errs:?}"); if cfg!(after){assert!(errs.is_empty())}else{assert!(!errs.is_empty())}
}
