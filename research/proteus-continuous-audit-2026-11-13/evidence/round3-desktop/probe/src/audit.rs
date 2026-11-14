use super::{agents::codex::*,transcript::*};
use std::{path::PathBuf,time::Duration};
use proteus_codex_client::Launch;

// A deterministic Codex wire peer, no remote service, auth, or model.
const PEER: &str = r#"
import json,sys,os,time
resumes=0
for line in sys.stdin:
    m=json.loads(line)
    if 'id' not in m: continue
    method=m.get('method'); p=m.get('params',{})
    if method=='initialize': result={}
    elif method=='thread/resume':
        resumes+=1
        result={'thread':{'id':'a','cwd':'/synthetic','turns':[],'status':{'type':'active'}}}
    elif method=='thread/turns/list': result={'data':[{'id':'t','status':'inProgress','items':[]}],'nextCursor':None}
    elif method=='thread/items/list':
        if resumes>1:
            print(json.dumps({'method':'item/agentMessage/delta','params':{'threadId':'a','turnId':'t','itemId':'i','delta':' world'}}),flush=True)
            if len(sys.argv)>1:
                end=time.monotonic()+2
                while not os.path.exists(sys.argv[1]):
                    if time.monotonic()>end: raise RuntimeError('delta acknowledgment timed out')
                    time.sleep(0.001)
        # AgentMessage carries text and opaque id, but no status field.
        result={'data':[{'turnId':'t','item':{'id':'i','type':'agentMessage','text':'Hello' if resumes==1 else 'Hello missed world'}}],'nextCursor':None}
    elif method=='thread/unsubscribe': result={}
    elif method=='thread/delete':
        print(json.dumps({'id':m['id'],'error':{'code':-32000,'message':'rejected deletion'}}),flush=True)
        continue
    elif method=='turn/interrupt':
        print(json.dumps({'method':'item/agentMessage/delta','params':{'threadId':'a','turnId':'t','itemId':'i','delta':' world'}}),flush=True)
        result={}
    else: result={}
    print(json.dumps({'id':m['id'],'result':result}),flush=True)
"#;
fn peer(gate:Option<&std::path::Path>) -> CodexService {
 let mut launch=Launch::codex(PathBuf::from("python3"),std::env::current_dir().unwrap());
 launch.args=vec!["-u".into(),"-c".into(),PEER.into()];
 if let Some(gate)=gate {launch.args.push(gate.to_string_lossy().into_owned());}
 launch.limits.request_timeout=Duration::from_secs(3);
 CodexService::launch(launch).unwrap()
}
fn apply(tr:&mut Transcript,event:Event) {
 match event {
  Event::ItemUpsert(i)=>{tr.external_upsert(i);},
  Event::TextDelta{id,turn_id,delta}=>{tr.external_delta(&turn_id,&id,&delta,false,false);},
  Event::Resynced{history,..}=>{for i in history {tr.external_upsert(i);}},
  _=>{}
 }
}
#[test]
fn active_history_snapshot_ignores_following_delta() {
 let service=peer(None); let open=service.resume("a").unwrap();
 assert_eq!(open.handle.current_turn().as_deref(),Some("t"));
 let mut tr=Transcript::default();
 for i in open.history.data {tr.external_upsert(i);}
 println!("resumed active row streaming={}",tr.entries()[0].streaming);
 open.handle.interrupt("t").unwrap();
 let event=open.events.recv_blocking().unwrap();
 assert!(matches!(event,Event::TextDelta{..})); apply(&mut tr,event);
 println!("after continuation {:?}",tr.entries()[0].text);
 assert_eq!(&*tr.entries()[0].text,"Hello world","active resumed row must accept further deltas");
}
#[test]
fn resync_delta_must_not_discard_authoritative_prefix() {
 let gate=std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!("delta-ack-{}",uuid::Uuid::new_v4()));
 let service=peer(Some(&gate)); let open=service.resume("a").unwrap();
 let mut tr=Transcript::default();
 // Existing live UI before unsubscribe holds a genuinely streaming prefix.
 for mut i in open.history.data {i.status="inProgress".into(); tr.external_upsert(i);}
 let mut saw=false;
 std::thread::scope(|scope| {
 let deleting=scope.spawn(|| service.delete_thread("a"));
 for _ in 0..5 {
   let event=open.events.recv_blocking().unwrap();
   let done=matches!(event,Event::Resynced{..});
   println!("recovery event: {:?}",event);
   if matches!(event,Event::TextDelta{..}) {std::fs::write(&gate,b"ack").unwrap();}
   apply(&mut tr,event);
   if done {saw=true;break;}
 }
 assert!(deleting.join().unwrap().is_err());
 });
 let _=std::fs::remove_file(&gate);
 assert!(saw);
 println!("after repair {:?}",tr.entries()[0].text);
 assert_eq!(&*tr.entries()[0].text,"Hello missed world","live delta does not contain missed prefix from detached interval");
}

#[test]
fn resume_overlap_must_not_replay_tool_delta_already_in_history() {
 let script = r#"
import json,sys
for line in sys.stdin:
    m=json.loads(line)
    if 'id' not in m: continue
    method=m.get('method')
    if method=='thread/resume': result={'thread':{'id':'a','cwd':'/synthetic','turns':[],'status':{'type':'active'}}}
    elif method=='thread/turns/list': result={'data':[{'id':'t','status':'inProgress','items':[]}],'nextCursor':None}
    elif method=='thread/items/list':
        print(json.dumps({'method':'item/commandExecution/outputDelta','params':{'threadId':'a','turnId':'t','itemId':'i','delta':' world'}}),flush=True)
        result={'data':[{'turnId':'t','item':{'id':'i','type':'commandExecution','command':'synthetic','cwd':'/synthetic','status':'inProgress','aggregatedOutput':'Hello world'}}],'nextCursor':None}
    else: result={}
    print(json.dumps({'id':m['id'],'result':result}),flush=True)
"#;
 let mut launch=Launch::codex(PathBuf::from("python3"),std::env::current_dir().unwrap());
 launch.args=vec!["-u".into(),"-c".into(),script.into()];
 launch.limits.request_timeout=Duration::from_secs(3);
 let service=CodexService::launch(launch).unwrap();
 let open=service.resume("a").unwrap();
 let mut tr=Transcript::default();
 for i in open.history.data {tr.external_upsert(i);}
 let event=open.events.recv_blocking().unwrap();
 let Event::ToolOutputDelta {id,turn_id,delta}=event else {panic!("wrong event")};
 tr.external_delta(&turn_id,&id,&delta,false,true);
 let output=tr.entries()[0].tool.as_ref().unwrap().result.as_deref().unwrap();
 println!("overlapped output: {output:?}");
 assert_eq!(output,"Hello world","snapshot already contains this buffered output delta");
}
