// Test-only typed storage primitive. No replacement of production revision,
// Snapshot::open, Drop, read-conversation handling, or Tokio synchronization.
use proteus_contracts::contracts::{ModelContextObservation,SessionLocator,SessionStorageFailure};
use std::sync::{OnceLock,Weak,atomic::{AtomicU8,AtomicUsize,Ordering}};
use std::thread::ThreadId;
use uuid::Uuid;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum TestMode { Lease,Good,WrongResponse,WrongSession,WorkerError,ReleaseError,WrongConversation }
pub(crate) struct TestIo {
    mode:TestMode, session:SessionLocator, snapshot:StorageSnapshot, caller:ThreadId,
    writer:OnceLock<Weak<tokio::sync::Mutex<RemoteWriter>>>,
    count:AtomicUsize, events:[AtomicU8;32], free:[AtomicU8;32], same_thread:[AtomicU8;32]
}
impl TestIo {
    fn record(&self,k:u8){
        let i=self.count.fetch_add(1,Ordering::SeqCst);assert!(i<32);
        self.events[i].store(k,Ordering::SeqCst);
        let w=self.writer.get().unwrap().upgrade().unwrap();
        self.free[i].store(w.try_lock().is_ok() as u8,Ordering::SeqCst);
        self.same_thread[i].store((std::thread::current().id()==self.caller) as u8,Ordering::SeqCst);
    }
    pub(crate) fn n_events(&self)->usize {self.count.load(Ordering::SeqCst)}
    pub(crate) fn trace(&self)->Vec<&'static str>{(0..self.n_events()).map(|i| match self.events[i].load(Ordering::SeqCst){1=>"open",2=>"read",3=>"release",_=>panic!("invalid trace")}).collect()}
    pub(crate) fn free_at_calls(&self)->Vec<bool>{(0..self.n_events()).map(|i|self.free[i].load(Ordering::SeqCst)==1).collect()}
    pub(crate) fn caller_at_calls(&self)->Vec<bool>{(0..self.n_events()).map(|i|self.same_thread[i].load(Ordering::SeqCst)==1).collect()}
    pub(crate) fn delegated_messages()->Vec<CanonicalMessage>{
        let mut message=CanonicalMessage::text(proteus_contracts::model_standard::MessageRole::System,"durable-only");
        message.id=Uuid::from_u128(701);message.parts[0].part_id=Uuid::from_u128(702);
        vec![message]
    }
}
#[async_trait::async_trait]
impl SessionStorage for TestIo {
    async fn execute(&self, _request:Request)->Result<Response>{anyhow::bail!("unexpected async worker request")}
    fn execute_blocking(&self,request:Request)->Result<Response>{
        request.validate()?;
        let response=match &request{
            Request::OpenSnapshot{session}=>{
                assert_eq!(*session,self.session);self.record(1);
                match self.mode{
                    TestMode::WrongResponse=>return Ok(Response::Done),
                    TestMode::WrongSession=>{let mut s=self.snapshot.clone();s.session.session_id=Uuid::from_u128(191);return Ok(Response::Snapshot{snapshot:s})},
                    TestMode::WorkerError=>return Err(SessionStorageFailure::MissingSession.into()),
                    _=>Response::Snapshot{snapshot:self.snapshot.clone()}
                }
            },
            Request::ReadConversation{snapshot,point}=>{
                assert_eq!(snapshot,&self.snapshot);assert_eq!(point,&StorageHistoryPoint::Current);self.record(2);
                if self.mode==TestMode::WrongConversation{return Ok(Response::Done)}
                Response::Conversation{conversation:StorageConversation{messages:Self::delegated_messages(),revision:self.snapshot.revision,model_context:vec![ModelContextObservation::HistoryCompacted]}}
            },
            Request::ReleaseSnapshot{snapshot}=>{
                assert_eq!(snapshot,&self.snapshot);self.record(3);
                if self.mode==TestMode::ReleaseError{return Err(SessionStorageFailure::MissingSession.into())}
                Response::Done
            },
            _=>anyhow::bail!("unexpected request in fixture"),
        };
        request.validate_response(&response)?;
        Ok(response)
    }
}
impl RemoteSessionStore {
    pub(crate) fn fixture(mode:TestMode)->(Self,Arc<TestIo>){
        let session=SessionLocator{session_id:Uuid::from_u128(71),key:"session-71".into()};
        let snapshot=StorageSnapshot{session:session.clone(),revision:StorageRevision{session_seq:91,history_revision:73},snapshot_id:"fixed-91".into(),content_sha256:"a".repeat(64)};
        let descriptor=StorageSessionDescriptor{session:session.clone(),parent_session_id:None,workspace_path:"/workspace".into(),local_path:Some("/durable/session".into()),record_location:None,created_at_ms:0,updated_at_ms:0};
        let io=Arc::new(TestIo{mode,session:session.clone(),snapshot,caller:std::thread::current().id(),writer:OnceLock::new(),count:Default::default(),events:Default::default(),free:Default::default(),same_thread:Default::default()});
        let store=Self::from_descriptor(io.clone(),Response::Session{descriptor}).unwrap();
        io.writer.set(Arc::downgrade(&store.writer)).ok().unwrap();
        if mode==TestMode::Lease{
            store.writer.try_lock().unwrap().fixture_lease(StorageWriterLease{session,token:Uuid::from_u128(1),generation:Uuid::from_u128(2)});
        }
        (store,io)
    }
    pub(crate) async fn park(&self)->impl Drop + '_ {self.writer.lock().await}
    pub(crate) fn writer_available(&self)->bool {self.writer.try_lock().is_ok()}
    pub(crate) fn reopen_fixture(&self)->Self {Self::from_descriptor(self.service.clone(),Response::Session{descriptor:self.descriptor.clone()}).unwrap()}
}
