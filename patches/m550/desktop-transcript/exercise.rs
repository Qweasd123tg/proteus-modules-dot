use crate::{app_protocol::*,domain::MessageId,meter::measure,transcript::{Change,Transcript}};
use std::{collections::hash_map::DefaultHasher,hash::{Hash,Hasher},sync::Arc};
use serde_json::{json,Value};
use std::cell::Cell;
thread_local! {pub static VISITS: Cell<usize> = const { Cell::new(0) };}
pub fn visit(){VISITS.with(|x| x.set(x.get()+1));}

fn msg(kind:usize, i:usize) -> AppTranscriptMessage {
 let label=||format!("идентичность:{i:010}:{}", "x".repeat(72));
 let (role,message_id)=match kind {0|1=>("system",None),2=>("assistant",Some(MessageId::from_u128(i as u128+1))),3=>("reasoning",Some(MessageId::from_u128(i as u128+1))),_=>("user",None)};
 AppTranscriptMessage{role:role.into(),message_id,phase:None,text:format!("payload/{i}/ф"),images:vec![],streaming:i%2==0,timestamp_ms:Some(1000+i as i64),
 tool:(kind==0).then(||AppTranscriptTool{call_id:label(),name:"tool".into(),args:json!({"val":i}),effective_args:None,status:"done".into(),result:Some(format!("result/{i}")),metadata:Value::Null,terminal:None}),
 subagent:(kind==1).then(||AppTranscriptSubagent{child_thread_id:label(),session:None,role:"child".into(),description:None,status:"settled".into(),iterations:Some(2),tools:vec![]})}
}
fn digest(t:&Transcript)->u64{
 let mut h=DefaultHasher::new();
 for e in t.entries() {
 e.key.hash(&mut h);e.role.hash(&mut h);e.message_id.hash(&mut h);e.text.hash(&mut h);
 e.time.hash(&mut h);e.streaming.hash(&mut h);format!("{:?}/{:?}/{:?}",e.tool,e.subagent,e.images).hash(&mut h);
 }
 h.finish()
}
fn oracle(){
 let mut t=Transcript::default();assert_eq!(t.reset(vec![]),Change::None);
 let mut first=msg(0,1);first.text="first".into();
 let mut last=msg(0,1);last.text="last".into();last.timestamp_ms=Some(800);
 let sub=msg(1,1);
 let ar=msg(2,2);let re=msg(3,2);let anon=msg(4,3);
 let mut idprio=msg(0,5);idprio.message_id=Some(MessageId::from_u128(6));
 let mut toolprio=msg(0,6);toolprio.subagent=msg(1,1).subagent;
 let old=vec![first.clone(),last.clone(),sub.clone(),ar.clone(),re.clone(),anon.clone(),idprio.clone(),toolprio.clone()];
 assert_eq!(t.reset(old.clone()),Change::Spliced{start:0,removed:0,inserted:8});
 let initial:Vec<_>=t.entries().iter().map(|e|(e.key,Arc::clone(&e.text))).collect();
 let mut d1=last.clone();d1.timestamp_ms=None;let mut d2=first.clone();d2.timestamp_ms=None;
 let mut changed=ar.clone();changed.text="changed".into();changed.timestamp_ms=None;
 let changed_priorities = {let mut x=idprio.clone();x.tool=msg(0,9999).tool;x};
 let mut toolpri=toolprio.clone();toolpri.subagent=msg(1,100).subagent;
 let mixed=vec![d1.clone(),d2,sub.clone(),re.clone(),changed,anon.clone(),changed_priorities.clone(),toolpri];
 assert_eq!(t.reset(mixed),Change::Spliced{start:0,removed:8,inserted:8});
 let e=t.entries();
 assert_eq!(e.iter().map(|i|i.key).collect::<Vec<_>>(),vec![2,10,3,5,4,6,7,8]);
 for (i,j) in [(0,1),(2,2),(3,4),(5,5),(6,6),(7,7)] {assert!(Arc::ptr_eq(&e[i].text,&initial[j].1));}
 assert!(!Arc::ptr_eq(&e[4].text,&initial[3].1));assert_eq!(e[0].time,Some(800));
 // A duplicate not assigned a key can still inherit a local time by role + content.
 assert_eq!(e[1].time,Some(1001));
 let mut page=t.empty_window();assert_eq!(page.append_page(vec![d1.clone(),d1.clone(),sub.clone(),changed_priorities],&t),Change::Spliced{start:0,removed:0,inserted:4});
 let p=page.entries(); assert_eq!(p.iter().map(|e|e.key).collect::<Vec<_>>(),vec![2,2,3,7]);
 assert!(Arc::ptr_eq(&p[0].text,&e[0].text)&&Arc::ptr_eq(&p[1].text,&e[0].text));assert_eq!(p[0].time,Some(800));
 // Last eligible UNIDENTIFIED old row wins even when it has a tool ID; time=0 is valid.
 let mut local=Transcript::default();
 let mut a=msg(4,1);a.text="共同".into();a.timestamp_ms=Some(1);
 let mut wrong=a.clone();wrong.role="reasoning".into();wrong.timestamp_ms=Some(13);
 let mut b=a.clone();b.timestamp_ms=Some(0);
 let mut c=b.clone();c.timestamp_ms=None;
 let mut systool=msg(0,111);systool.text="sys".into();systool.timestamp_ms=Some(-1);
 let mut suffix=msg(2,9);suffix.text="共同".into();suffix.timestamp_ms=Some(999);
 local.reset(vec![a,wrong,b,c,systool,suffix]);
 let mut one=msg(4,90);one.message_id=Some(MessageId::from_u128(77));one.timestamp_ms=None;one.text="共同".into();
 let mut two=one.clone(); two.role="reasoning".into();two.message_id=Some(MessageId::from_u128(78));
 let mut three=two.clone();three.role="system".into();three.text="sys".into();
 let mut four=one.clone();four.timestamp_ms=Some(234);four.message_id=Some(MessageId::from_u128(79));
 let mut five=one.clone();five.text="absent".into();five.message_id=Some(MessageId::from_u128(80));
 local.reset(vec![one,two,three,four,five]);assert_eq!(local.entries().iter().map(|e|e.time).collect::<Vec<_>>(),vec![Some(0),Some(13),Some(-1),Some(234),None]);
 println!("oracle {} {} {}", digest(&t),digest(&page),digest(&local));
}
pub fn run() {
 oracle();
 let mut t=Transcript::default();
 let input:Vec<_>=(0..50000).map(|i|msg(i%4,i)).collect();let wire=input.clone();
 let (ch,first)=measure(||t.reset(wire));assert_eq!(ch,Change::Spliced{start:0,removed:0,inserted:50000});
 println!("cold {} {} {}",first.requests,first.bytes,digest(&t));
 let tiny=input[49_950..].to_vec();let (ch,next)=measure(||t.reset(input));assert_eq!(ch,Change::None);println!("refresh {} {} {}",next.requests,next.bytes,digest(&t));
 let mut page=t.empty_window();let (ch,next)=measure(||page.append_page(tiny,&t));assert_eq!(ch,Change::Spliced{start:0,removed:0,inserted:50});println!("page {} {} {}",next.requests,next.bytes,digest(&page));
 let n=2048;let seq=|start|->Vec<_>{(start..start+n).map(|i|{let mut e=msg(2,i);e.timestamp_ms=None;e}).collect()};
 let mut tail=Transcript::default();tail.reset(seq(0));let displaced=seq(10_000);VISITS.with(|x|x.set(0));let (ch,mem)=measure(||tail.reset(displaced));assert_eq!(ch,Change::Spliced{start:0,removed:n,inserted:n});assert!(tail.entries().iter().all(|e|e.time.is_none()));
 println!("disjoint {} {} {} {}",mem.requests,mem.bytes,digest(&tail),VISITS.with(Cell::get));
}
