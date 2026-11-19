#[cfg(unix)]
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn perf6_paged_history_over_route() {
    use crate::model_standard::{CanonicalMessage, MessageRole};
    use proteus_contracts::app_protocol::AppTranscriptPage;
    let cases = std::env::var("PERF6_CASES").unwrap_or("100,1000,5000".into());
    let reps: usize= std::env::var("PERF6_REPS").unwrap_or("3".into()).parse().unwrap();
    for n in cases.split(',').map(|n| n.parse::<usize>().unwrap()) {
        let (mut state, server, _dir) = test_state().await;
        let counts=std::sync::Arc::new(Perf6PagingRequests{inner:state.storage_service().unwrap(),counts:Default::default()});
        if std::env::var_os("PERF6_COUNTS").is_some(){state.storage=Some(counts.clone());}
        server.start_session().await.unwrap();
        let store = server.runtime.session_store().unwrap();
        let thread = crate::domain::new_thread_id();
        let msgs = (0..n).map(|i| CanonicalMessage::text(if i%2==0 {MessageRole::User} else {MessageRole::Assistant}, format!("page {i}: synthetic café {}", "q".repeat(64)))).collect::<Vec<_>>();
        for chunk in msgs.chunks(100) {store.append_history(thread,None,chunk).await.unwrap();}
        drop(msgs);
        let start=std::time::Instant::now();
        let completed=crate::app_server::read_model::project_completed_transcript(store).unwrap();
        assert_eq!(completed.messages.len(),50);
        let cursor=completed.cursor.unwrap();
        let rev=cursor.revision;
        assert_eq!(cursor.before,n-50);
        let base=format!("/history/page?session_dir={}",store.session_dir().display());
        let elapsed=start.elapsed();
        println!("PREP n={n} projection_ms={:.2}",elapsed.as_secs_f64()*1e3);
        {
            let mut sizes=vec![];
            for ent in std::fs::read_dir(store.session_dir()).unwrap(){
                let ent=ent.unwrap(); if !ent.file_name().to_string_lossy().starts_with(".storage-cache-"){continue;}
                let doc:serde_json::Value=serde_json::from_slice(&std::fs::read(ent.path()).unwrap()).unwrap(); let val=&doc["value"];
                if let Some(pages)=val.pointer("/transcript/pages").and_then(|v|v.as_array()) && val.pointer("/transcript/rows").and_then(|x|x.as_u64())==Some(n as u64){
                    sizes.push((serde_json::to_vec(val).unwrap().len(),pages.len(),val.pointer("/conversation/pages").unwrap().as_array().unwrap().len(),val.pointer("/context/pages").unwrap().as_array().unwrap().len()));
                }
            }
            sizes.sort(); assert!(!sizes.is_empty()); println!("MANIFEST n={n} (json_bytes, transcript_pages, conversation_pages, context_pages)={:?}",sizes);
        }
        let skip=std::env::var_os("PERF6_SKIP_SWEEP").is_some();
        for rep in 0..=reps {
            for (label,before,cursor) in [("head",n,false),("tail",n,true),("middle",n/2,true),("oldest",50,true)] {
                let path=if cursor {format!("{base}&before={before}&revision={rev}")} else {base.clone()};
                let start=std::time::Instant::now();
                let res=route_request(state.clone(),authed_get_request(&path)).await.unwrap();
                assert_eq!(res.status(),StatusCode::OK,"{path}");
                let body=response_bytes(res).await;
                let page:AppTranscriptPage=serde_json::from_slice(&body).unwrap();
                let ns=start.elapsed().as_nanos();
                assert_eq!((page.total,page.start,page.messages.len(),page.revision.as_str()),(n,before-50,50,rev.as_str()));
                for (i,msg) in page.messages.iter().enumerate() {assert_eq!(msg.text,format!("page {}: synthetic café {}",i+page.start,"q".repeat(64)));}
                println!("PAGE n={n} rep={rep} pos={label} ns={ns} bytes={}",body.len());
                if std::env::var_os("PERF6_COUNTS").is_some(){println!("COUNTS n={n} rep={rep} pos={label} calls={:?}",std::mem::take(&mut *counts.counts.lock().unwrap()));}
            }
        }
        if !skip {
           let start=std::time::Instant::now(); let mut pos=n; let mut bytes=0;
           while pos>0 {
             let path=format!("{base}&before={pos}&revision={rev}");
             let res=route_request(state.clone(),authed_get_request(&path)).await.unwrap();
             assert_eq!(res.status(),StatusCode::OK); let data=response_bytes(res).await; bytes+=data.len();
             let page:AppTranscriptPage=serde_json::from_slice(&data).unwrap();
             assert_eq!(page.start+page.messages.len(),pos);
             for (i,m) in page.messages.iter().enumerate(){assert_eq!(m.text,format!("page {}: synthetic café {}",i+page.start,"q".repeat(64)));}
             pos=page.start;
           } println!("SWEEP n={n} ns={} bytes={bytes}",start.elapsed().as_nanos());
        }
        if let Some(client)=std::env::var_os("PERF6_CLIENT") {
            let listener=TcpListener::bind("127.0.0.1:0").await.unwrap(); let addr=listener.local_addr().unwrap();
            let task=tokio::spawn(async move {loop {let (stream,_)=listener.accept().await.unwrap();let state=state.clone();tokio::spawn(async move {let svc=service_fn(move |req|route_request(state.clone(),req));let _=http1::Builder::new().serve_connection(TokioIo::new(stream),svc).await;});}});
            let dir=store.session_dir().to_owned();
            let status=tokio::task::spawn_blocking(move||std::process::Command::new(client).arg(format!("http://{addr}")).arg(dir).arg(n.to_string()).arg(rev).status().unwrap()).await.unwrap();
            task.abort(); assert!(status.success());
        }
        server.shutdown().await;
    }
}

struct Perf6PagingRequests {
    inner: crate::core::StorageService,
    counts: std::sync::Mutex<std::collections::BTreeMap<&'static str, usize>>,
}
impl Perf6PagingRequests {
    fn observe(&self,req:&crate::contracts::SessionStorageRequest){
        use crate::contracts::SessionStorageRequest::*;
        let k=match req {
            Open {..}=>"open", ReadCache{key,..} if key.starts_with("display-revision-")=>"read_revision_manifest",
            ReadCache{key,..} if key=="display-view-v1-head"=>"read_current_manifest",
            ReadCache{key,..} if key.starts_with("display-data-")=>"read_data_page",
            OpenSnapshot{..}=>"open_snapshot", ReadRecords{..}=>"read_journal_records", _=>"other",
        }; *self.counts.lock().unwrap().entry(k).or_default()+=1;
    }
}
#[async_trait::async_trait]
impl crate::contracts::SessionStorage for Perf6PagingRequests {
    async fn execute(&self,r:crate::contracts::SessionStorageRequest)->anyhow::Result<crate::contracts::SessionStorageResponse>{
       self.observe(&r);self.inner.execute(r).await
    }
    fn execute_blocking(&self,r:crate::contracts::SessionStorageRequest)->anyhow::Result<crate::contracts::SessionStorageResponse>{
       self.observe(&r);self.inner.execute_blocking(r)
    }
}
