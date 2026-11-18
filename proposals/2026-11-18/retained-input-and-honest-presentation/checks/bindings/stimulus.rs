fn configure(v:&mut DeclarativeView,c:&mut Context<DeclarativeView>,id:&str,lines:usize,a:&str,s:Option<&str>,grow:bool){
  v.prepare(&Node::Input{id:id.into(),value:"unchanged from source".into(),placeholder:"keep text".into(),action:a.into(),lines,submit:s.map(String::from),search:false},grow,&mut Window,c)
}
fn event(v:&mut DeclarativeView,c:&mut Context<DeclarativeView>,id:&str,event:InputEvent)->Option<String>{
  let e=v.fields.inputs[id].state.e();let h=c.handlers[&e.id()].clone();let count=v.sent.len();
  h(v,&event,c);v.sent.get(count).map(|(action,text)|{assert_eq!(text.as_str(),Some("uncommitted draft"));action.clone()})
}
fn main(){
  let mut c=Context{handlers:HashMap::new(),_t:std::marker::PhantomData};let mut v=DeclarativeView::default();
  configure(&mut v,&mut c,"search",1,"s0",Some("submit0"),false);configure(&mut v,&mut c,"notes",3,"n0",None,false);
  let line_id=v.fields.inputs["search"].state.e().id();let area_id=v.fields.inputs["notes"].state.e().id();
  for id in ["search","notes"]{v.fields.inputs[id].state.e().0.borrow_mut().value="uncommitted draft".into();}
  let mut d=0;let mut e=0;let mut z=0;let mut n=0;
  for i in 0..12 {
    let sl=if i%3==0{Some("save")}else if i%3==1{None}else{Some("apply")};
    let sa=if i%2==0{"sa"}else{"sb"};
    let nl=if i%3==0{None}else if i%3==1{Some("post")}else{Some("send")};
    let na=if i%2==0{"na"}else{"nb"};
    let nlines=[6,2,40,3][i%4];
    configure(&mut v,&mut c,"search",1,sa,sl,false);configure(&mut v,&mut c,"notes",nlines,na,nl,i>=6);
    assert_eq!(c.handlers.len(),2); assert_eq!(line_id,v.fields.inputs["search"].state.e().id());assert_eq!(area_id,v.fields.inputs["notes"].state.e().id());
    for id in ["search","notes"]{assert_eq!(v.fields.inputs[id].state.e().read(&c).value().as_ref(),"uncommitted draft");}
    if v.fields.inputs["notes"].state.e().read(&c).min!=nlines{z+=1};
    for (id,a,s,m) in [("search",sa,sl,false),("notes",na,nl,true)]{
      for (ev,vexp) in [(InputEvent::Change,Some(a)),(InputEvent::PressEnter{secondary:m},s),(InputEvent::PressEnter{secondary:!m},None),(InputEvent::Other,None)]{
        n+=1;if event(&mut v,&mut c,id,ev).as_deref()!=vexp {e+=1}
      }
    }
    if v.fields.inputs["notes"].state.e().read(&c).min!=nlines{d+=1};
  }
  println!("{n} events; wrong target/submit: {e}; bad minimum after definition: {z}/12; after edit: {d}/12; two editor IDs, two subscriptions and both unmatched drafts preserved throughout");
  if cfg!(candidate) {assert_eq!((e,z,d),(0,0,0));} else {assert!(e>0&&d>0);}
}
