use std::collections::HashSet;
use serde_json::{Value,json};
fn checkbox_value(next: Vec<Value>, saved: Option<&Value>) -> Value {
    if let Some(original) = saved.and_then(Value::as_array)
        && original.len() == next.len()
        && original != &next
    {
        let mut remaining: HashSet<_> = next.iter().collect();
        if original.iter().all(|value| remaining.remove(value)) {
            return Value::Array(original.clone());
        }
    }
    Value::Array(next)
}

fn arrays(a:&[Value],n:usize,out:&mut Vec<Vec<Value>>,x:&mut Vec<Value>){out.push(x.clone());if n>0{for v in a{x.push(v.clone());arrays(a,n-1,out,x);x.pop();}}}
fn main(){let mut data=Vec::new();arrays(&[json!("alpha"),json!("β"),json!(7),json!(null),json!({"k":1}),json!([true])],3,&mut data,&mut vec![]);
let mut count=0;let mut restored=0;for original in &data{for now in &data{
 let saved=Value::Array(original.to_vec());
 let unique=original.iter().enumerate().all(|(i,v)|!original[..i].contains(v))&&now.iter().enumerate().all(|(i,v)|!now[..i].contains(v));
 let agree=unique&&original.len()==now.len()&&now.iter().all(|v|original.contains(v));
 let wanted=if agree{original}else{now};
 let got=checkbox_value(now.to_vec(),Some(&saved));
 assert_eq!(got.as_array().unwrap(),wanted);
 assert_eq!(checkbox_value(now.to_vec(),None).as_array().unwrap(),now);
 assert_eq!(checkbox_value(now.to_vec(),Some(&json!({"scalar":"context"}))).as_array().unwrap(),now);
 if now!=original&&agree{restored+=1;}count+=1;
}}println!("{count} independent pairs over strings/Unicode/number/null/object/array; {restored} distinct permutations restored. Absent/non-array, changed membership and duplicate controls unchanged.");}
