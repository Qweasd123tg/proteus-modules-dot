use std::alloc::{GlobalAlloc, Layout, System};
use std::cell::Cell;
struct Meter;
thread_local!{static METER: Cell<Option<(usize,usize,isize,isize)>> = const { Cell::new(None) };}
fn charge(n:usize,delta:isize,alloc:bool){
    let _=METER.try_with(|c|if let Some((count,bytes,live,peak))=c.get(){
        let now=live+delta;
        c.set(Some((count+usize::from(alloc),bytes+n,now,peak.max(now))));
    });
}
unsafe impl GlobalAlloc for Meter{
 unsafe fn alloc(&self,l:Layout)->*mut u8{let p=unsafe{System.alloc(l)}; if !p.is_null(){charge(l.size(),l.size() as isize,true)} p}
 unsafe fn alloc_zeroed(&self,l:Layout)->*mut u8{let p=unsafe{System.alloc_zeroed(l)};if !p.is_null(){charge(l.size(),l.size() as isize,true)} p}
 unsafe fn realloc(&self,p:*mut u8,l:Layout,n:usize)->*mut u8{let p=unsafe{System.realloc(p,l,n)};if !p.is_null(){charge(n,n as isize-l.size() as isize,true)} p}
 unsafe fn dealloc(&self,p:*mut u8,l:Layout){charge(0,-(l.size() as isize),false);unsafe{System.dealloc(p,l)}}
}
#[global_allocator] static ALLOC:Meter=Meter;

#[test]
fn wire_selected_history_budget_and_allocator(){
 use proteus_contracts::contracts::{ExecutionAttribution,HookEvent,HookInput,HookResponse};
 use proteus_contracts::model_standard::{CanonicalPart,PartProvenance,PartScope};
 use proteus_contracts::process_module::HookModule;
 for old_count in [0,32,128]{
    let old="o".repeat(8192);
    let mut rows:Vec<_>=(0..old_count).map(|_|CanonicalMessage::text(MessageRole::User,old.clone())).collect();
    let ctx=CanonicalMessage::from_parts(MessageRole::User,vec![CanonicalPart::new(PartProvenance::ContextBuilder,PartScope::Request,ContentPart::Text{text:"request-scoped context".into()})]);
    let user=CanonicalMessage::text(MessageRole::User,"A".repeat(79_996));
    let last=CanonicalMessage::text(MessageRole::User,"🙂");
    let ignored=CanonicalMessage::text(MessageRole::User,"  <turn_aborted>system insert");
    let generated=CanonicalMessage::text(MessageRole::User,format!("  {SUMMARY_PREFIX}\nsynthesized"));
    let assist=CanonicalMessage::text(MessageRole::Assistant,"ignore assistant");
    rows.extend([user.clone(),ignored,ctx.clone(),generated,assist,last.clone()]);
    let prepared=input(rows.clone(),90000).preparation();
    let prior=ContextPreparationOutput::unchanged(rows.clone());
    let hook=HookInput{event:HookEvent::BeforeContext{input:prepared,output:prior,model_capabilities:None,target:None},attribution:ExecutionAttribution::detached(proteus_contracts::domain::new_execution_id()),cwd:"/repo".into(),conversation:None};
    let serialized=serde_json::to_string(&hook).unwrap();
    let module=crate::CodexPreparationHook(crate::config::CompactorConfig::parse(&json!({"trigger_tokens":100})).unwrap());
    let mut host=TestHost::with_response("summary suffix");
    METER.with(|m|m.set(Some((0,0,0,0))));
    let resp=module.invoke_json(serialized,&mut host).unwrap();
    let (alloc,bytes,_,peak)=METER.with(|m|m.replace(None)).unwrap();
    let HookResponse::ContextPreparation{output}=serde_json::from_str(&resp).unwrap() else{panic!("missing replacement")};
    assert_eq!(output.messages.len(),4);
    assert_eq!(&output.messages[..3],&[user,ctx,last]);
    assert!(output.user_message_replacements.is_empty());
    assert_eq!(output.summary,Some(format!("{SUMMARY_PREFIX}\nsummary suffix")));
    assert_eq!(output.metadata["preserved_user_messages"],2);
    assert_eq!(output.metadata["ephemeral_context_messages"],1);
    assert_eq!(output.metadata["compacted_messages"],old_count+5);
    let requests=host.requests.lock().unwrap();
    assert_eq!(requests.len(),1);
    assert_eq!(&requests[0].messages[..rows.len()],rows.as_slice(),"preserve original model-summary input");
    println!("WIRE {old_count} {alloc} {bytes} {peak}");
 }
}
