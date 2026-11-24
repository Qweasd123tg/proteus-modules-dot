struct Sink {
 events:StdMutex<Vec<(&'static str,ExecutionAttribution,String)>>,
 gate:Mutex<()>,
 fail:AtomicBool,
}
impl Sink{
 fn new()->Self{ Self{events:Default::default(),gate:Default::default(),fail:Default::default()} }
 fn event(&self,event:&'static str,attribution:ExecutionAttribution,call:&str){
  self.events.lock().unwrap().push((event,attribution,call.to_owned()));
 }
 fn events(&self)->Vec<(&'static str,ExecutionAttribution,String)>{self.events.lock().unwrap().clone()}
}
#[derive(Debug)]struct SinkError;
impl std::fmt::Display for SinkError {fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result{f.write_str("typed recorder sink failed")}}
impl std::error::Error for SinkError{}
#[async_trait::async_trait]
impl ToolExecutionRecorder for Sink{
 async fn tool_call_requested(&self,a:ExecutionAttribution,_:OperationOwner,call:&ToolCall)->Result<()>{self.event("requested",a,&call.id);Ok(())}
 async fn tool_call_resolved(&self,a:ExecutionAttribution,call:&ToolCall,_:&ToolCallResolution)->Result<()>{self.event("resolved",a,&call.id);Ok(())}
 async fn tool_approval_requested(&self,a:ExecutionAttribution,call:&ToolCall,_:&str)->Result<()>{self.event("approval",a,&call.id);Ok(())}
 async fn tool_effect_recorded(&self,a:ExecutionAttribution,result:&ToolResult)->Result<()>{self.event("raw",a,&result.call_id);Ok(())}
 async fn tool_result_recorded(&self,a:ExecutionAttribution,result:&ToolResult)->Result<()>{
  self.event("final-enter",a,&result.call_id);
  let _locked=self.gate.lock().await;
  if self.fail.load(Ordering::SeqCst){
   self.event("final-error",a,&result.call_id);
   return Err(SinkError.into());
  }
  self.event("final-ok",a,&result.call_id);Ok(())
 }
}
struct ProbeStorage(AtomicUsize);
#[async_trait::async_trait]
impl SessionStorage for ProbeStorage{
 async fn execute(&self,_:Request)->Result<Response>{bail!("unexpected persisted store async operation")}
 fn execute_blocking(&self,req:Request)->Result<Response>{
  req.validate()?;
  let Request::Open {path}=&req else{bail!("unexpected persisted store blocking operation")};
  self.0.fetch_add(1,Ordering::SeqCst);
  assert_eq!(path,Path::new("/fixture/session"));
  let response=Response::Session{descriptor:StorageSessionDescriptor{
   session:SessionLocator{session_id:Uuid::from_u128(1),key:"fixture".into()},
   parent_session_id:None,workspace_path:"/fixture".into(),local_path:Some(path.clone()),record_location:None,created_at_ms:1,updated_at_ms:1
  }};
  req.validate_response(&response)?;Ok(response)
 }
}
