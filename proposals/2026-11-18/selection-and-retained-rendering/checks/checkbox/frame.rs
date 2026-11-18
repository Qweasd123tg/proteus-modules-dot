use serde_json::{Value,Map,json};
use std::collections::{BTreeMap,HashSet};
#[derive(Clone,Default,Debug,PartialEq)] struct Draft{config:BTreeMap<String,BTreeMap<String,Value>>}
struct FieldPath{slot:String,module:String,keys:Vec<String>}
impl Draft{
//DRAFT
}
//UTIL
struct SettingsView { baseline:Draft, draft:Draft }
impl SettingsView { fn edit_field(&mut self,path:&FieldPath,value:Option<Value>,default:Option<&Value>,_:&mut ()){ self.draft.edit_value(path,value,default,&self.baseline); } }
type App=SettingsView;struct Weak;
impl Weak{fn update<R>(&self,cx:&mut App,f:impl FnOnce(&mut SettingsView,&mut ())->R)->R{f(cx,&mut ())}}
struct Field{default:Option<Value>}struct FieldSpec{field:Field,path:FieldPath,view:Weak}
impl FieldSpec{
//METHODS
}
//HELPER
struct Choice{value:Value}
fn toggle(handler:&FieldSpec,cx:&mut App,options:&[Choice],value:Value,checked:&bool){
 let selected=cx.draft.value(&handler.path).or(handler.field.default.as_ref()).and_then(Value::as_array).cloned().unwrap_or_default();
 //CLICK
}
fn spec(default:Option<Value>)->FieldSpec{FieldSpec{field:Field{default},view:Weak,path:FieldPath{slot:"display".into(),module:"sample".into(),keys:vec!["box".into(),"labels".into()]}}}
fn initial(s:&FieldSpec,v:Option<Value>)->App{
 let mut b=Draft::default();b.config.entry("display".into()).or_default().insert("sample".into(),json!({"sibling":29}));
 b.set_value(&s.path,v);SettingsView{baseline:b.clone(),draft:b}
}
fn perms(v:&[Value],p:Vec<Value>,out:&mut Vec<Vec<Value>>){out.push(p.clone()); for x in v {if !p.contains(x){let mut q=p.clone();q.push(x.clone());perms(v,q,out);}}}
fn main(){
 let vals=vec![json!("Blue"),json!("Gold"),json!("Grey"),json!("Green")];
 let opts:Vec<_>=vals.iter().cloned().map(|value|Choice{value}).collect();
 let mut bs=Vec::new();perms(&vals,vec![],&mut bs);
 let(mut cases,mut fail)=(0,0);
 for base in bs {
  for saved in 0..3{
   let a=Value::Array(base.clone());let (initial_value,default)=match saved{0=>(Some(a.clone()),None),1=>(None,Some(a.clone())),_=>(Some(a.clone()),Some(a.clone()))};
   let s=spec(default);
   for target in &vals{
    let has=base.contains(target);
    let mut app=initial(&s,initial_value.clone());
    toggle(&s,&mut app,&opts,target.clone(),&!has);
    let edited=app.draft.value(&s.path).or(s.field.default.as_ref()).unwrap().as_array().unwrap();
    assert_eq!(edited.contains(target),!has);
    toggle(&s,&mut app,&opts,target.clone(),&has);
    if app.draft!=app.baseline{fail+=1;}
    assert_eq!(app.draft.module_config("display","sample").unwrap()["sibling"],29);
    cases+=1;
   }
  }
 }
 println!("{cases} two-click cycles; {fail} do not restore original draft");
 let s=spec(None);
 for (v,click,expected) in [(json!(["obsolete","Grey"]),json!("Blue"),json!(["Blue","Grey"])),(json!(["Grey","Grey"]),json!("Blue"),json!(["Blue","Grey"])),(json!(["Grey","Blue"]),json!("Gold"),json!(["Blue","Gold","Grey"]))]{
  let mut app=initial(&s,Some(v)); toggle(&s,&mut app,&opts,click,&true);assert_eq!(app.draft.value(&s.path),Some(&expected))
 }
 let mut app=initial(&s,None);let array=json!(["Grey","Blue"]);s.set(Some(array.clone()),&mut app);assert_eq!(app.draft.value(&s.path),Some(&array));
 if fail>0{std::process::exit(1);}
}
