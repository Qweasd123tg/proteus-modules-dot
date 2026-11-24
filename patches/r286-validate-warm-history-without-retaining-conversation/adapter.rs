const SESSION:Uuid=Uuid::from_u128(88);const THREAD:Uuid=Uuid::from_u128(9);
const HEAD:&str="display-view-v1-head";const PREFIX:&str="display-view-v1-prefix";
#[derive(Clone)]struct Service(Arc<Io>);
struct Io{
 descriptor:StorageSessionDescriptor,snapshot:StorageSnapshot,route:&'static str,
 records:Arc<Vec<JournalRecord>>,docs:Arc<Mutex<BTreeMap<String,StorageMetadataDocument>>>, fault:&'static str,
 open_count:AtomicUsize,expected_release:Mutex<Option<(StorageSnapshot,bool)>>,
}
#[derive(Clone)]pub(crate) struct RemoteSessionStore{
 descriptor:StorageSessionDescriptor,snapshot:StorageSnapshot,service:Service,
 records:Arc<Vec<JournalRecord>>,docs:Arc<Mutex<BTreeMap<String,StorageMetadataDocument>>>,
}
impl RemoteSessionStore{
 fn new(records:Arc<Vec<JournalRecord>>,route:&'static str,fault:&'static str,docs:Arc<Mutex<BTreeMap<String,StorageMetadataDocument>>>)->Self{
  let session=SessionLocator{session_id:SESSION,key:"r284-cold-repair".into()};
  let descriptor=StorageSessionDescriptor{session:session.clone(),parent_session_id:None,workspace_path:"/fixture".into(),local_path:Some("/fixture/session".into()),created_at_ms:1000,updated_at_ms:1001,record_location:None};
  let revision=StorageRevision{session_seq:records.len() as u64,history_revision:records.len() as u64};
  let snapshot=StorageSnapshot{session,snapshot_id:"fixed-repair".into(),content_sha256:"a".repeat(64),revision};
  let service=Service(Arc::new(Io{descriptor:descriptor.clone(),snapshot:snapshot.clone(),records:records.clone(),docs:docs.clone(),route,fault,open_count:AtomicUsize::new(0),expected_release:Mutex::new(None)}));
  Self{descriptor,snapshot,service,records,docs}
 }
 fn from_descriptor(service:Service,response:Response)->Result<Self>{
  let Response::Session{descriptor}=response else{bail!("storage returned an unexpected session response")};
  ensure!(descriptor.local_path.is_some(),"this client requires a session display locator");
  assert_eq!(descriptor,service.0.descriptor);
  Ok(Self{descriptor,snapshot:service.0.snapshot.clone(),records:service.0.records.clone(),docs:service.0.docs.clone(),service})
 }

}
#[async_trait::async_trait]
impl SessionStorage for Service{
 fn supports_display_projection(&self)->bool{self.0.route!="unsupported"}
 async fn execute(&self,_:Request)->Result<Response>{bail!("unexpected async request")}
 fn execute_blocking(&self,r:Request)->Result<Response>{self.0.request(r)}
}
impl Io{
 fn request(&self,req:Request)->Result<Response>{
  let display=matches!(&req,Request::ReadDisplayRecords{..});
  req.validate()?;
  let response=match &req{
   Request::Open{path}=>{
    assert_eq!(Some(path),self.descriptor.local_path.as_ref());trace("OpenSession".into());Response::Session{descriptor:self.descriptor.clone()}
   },
   Request::OpenSnapshot{session}=>{
    let final_=FINAL.replace(false);let index=self.open_count.fetch_add(1,Ordering::SeqCst);
    assert_eq!(*session,self.descriptor.session);
    trace(if final_{"FinalOpen"}else{"OpenSnapshot"}.into());
    let mut snapshot=self.snapshot.clone();
    if final_{
      match self.fault{
       "final-wrong-kind"=>return Ok(Response::Done),
       "final-wrong-session"=>{snapshot.session.session_id=Uuid::from_u128(177);return Ok(Response::Snapshot{snapshot});}
       "final-missing"=>return Err(SessionStorageFailure::MissingSession.into()),
       "final-transport"=>bail!("fixture worker disconnected"),
       "final-hash"=>snapshot.content_sha256="b".repeat(64),
       "final-revision"=>{snapshot.revision.history_revision+=1;snapshot.revision.session_seq+=1;},
       "final-new-handle"=>snapshot.snapshot_id="other-same-fingerprint".into(),
       _=>()
      }
    }else if index==0{
      match self.fault{
       "initial-hash"=>snapshot.content_sha256="c".repeat(64),
       "initial-wrong-kind"=>return Ok(Response::Done),
       "initial-wrong-session"=>{snapshot.session.session_id=Uuid::from_u128(193);return Ok(Response::Snapshot{snapshot});}
       "initial-missing"=>return Err(SessionStorageFailure::MissingSession.into()),
       _=>()
      }
    }
    assert!(self.expected_release.lock().unwrap().replace((snapshot.clone(),final_)).is_none());
    Response::Snapshot{snapshot}
   },
   Request::OpenDisplaySnapshot{session}=>{
    assert_eq!(*session,self.descriptor.session);trace("OpenDisplaySnapshot".into());
    let projection=if self.route=="projected"{Some(self.projected_state()?)}else{None};
    if let Some(ref p)=projection{assert!(self.expected_release.lock().unwrap().replace((p.snapshot.clone(),false)).is_none());}
    Response::DisplaySnapshot{projection}
   },
   Request::ReadRecords{snapshot,after_seq,limit} | Request::ReadDisplayRecords{snapshot,after_seq,limit}=>{
    assert_eq!(snapshot.session,self.descriptor.session);assert_eq!(*limit,64);assert_eq!(display,self.route=="projected");
    trace(format!("{} {after_seq}",if display{"ReadDisplayRecords"}else{"ReadRecords"}));
    let mut it=self.records.iter().filter(|r|r.session_seq>*after_seq && (!display||r.entry.kind().is_display_record()));
    let records:Vec<_>=it.by_ref().take(64).cloned().collect();let next_after_seq=it.next().map(|_|records.last().unwrap().session_seq);
    Response::Records{page:StorageRecordPage{snapshot:snapshot.clone(),records,next_after_seq}}
   }
   Request::ReleaseSnapshot{snapshot}=>{
    let (expected,final_)=self.expected_release.lock().unwrap().take().expect("matching checked open");
    assert_eq!(*snapshot,expected);assert_eq!(snapshot.session,self.descriptor.session);
    trace(if final_{"FinalRelease"}else{"ReleaseSnapshot"}.into());
    if (final_ && self.fault=="final-release") || (!final_ && self.fault=="initial-release"){return Err(SessionStorageFailure::MissingSession.into());}
    Response::Done
   },
   Request::Describe{session}=>{assert_eq!(*session,self.descriptor.session);trace("Describe".into());Response::Session{descriptor:self.descriptor.clone()}},
   Request::ReadCache{session,key,source}=>{
    assert_eq!(*session,self.descriptor.session);assert!(source.is_none());trace(format!("ReadCache {key}"));
    if std::thread::panicking(){panic!("unexpected read while unwinding")}
    if READ_FAULT.with(|f|f.borrow().as_ref()==Some(key)){
      return match self.fault{"storage-wrong-kind"=>Ok(Response::Done),"storage-failure"=>Err(SessionStorageFailure::MissingSession.into()),_=>unreachable!()};
    }
    Response::Metadata{document:self.docs.lock().unwrap().get(key).cloned()}
   },
   Request::WriteCache{session,key,source,value}=>{
    assert_eq!(*session,self.descriptor.session);assert_eq!(*source,self.snapshot);trace(format!("WriteCache {key}"));
    let failed=match self.fault{"page"=>key.starts_with("display-data-"),"prefix"=>key==PREFIX,"named-write"=>key.starts_with("display-revision-"),"head"=>key==HEAD,_=>false};
    if failed{Response::CacheWritten{etag:None}}else{
     let etag=storage_value_etag(value)?;self.docs.lock().unwrap().insert(key.clone(),StorageMetadataDocument{etag:etag.clone(),value:value.clone()});Response::CacheWritten{etag:Some(etag)}
    }
   }
   _=>bail!("unexpected typed fixture request")
  };
  // Core's in-process snapshot guards get the explicit malformed replies
  // above. All genuine/good protocol responses are independently validated.
  req.validate_response(&response)?;
  Ok(response)
 }
 fn projected_state(&self)->Result<StorageDisplaySnapshot>{
  let mut v=proteus_session_semantics::JournalValidationState::default();let mut u=proteus_session_semantics::UsageProjection::default();let mut c=proteus_session_semantics::ModelContextProjection::default();let mut next=1;
  for r in self.records.iter(){v.apply_sequenced(SESSION,r,&mut next)?;u.apply(r);c.apply(r);}
  ensure!(v.history_revision()==self.snapshot.revision.history_revision,"invalid fixture revision");
  let snapshot=self.snapshot.clone();
  let out=StorageDisplaySnapshot{snapshot,state:StorageResumeState{usage:u.snapshot(SESSION),last_history_turn:v.last_history_turn(),interrupted_turns:v.interrupted_turns(),conversation:StorageConversation{revision:self.snapshot.revision,messages:v.into_history(),model_context:c.snapshot()}}};
  Ok(out)
 }
}
