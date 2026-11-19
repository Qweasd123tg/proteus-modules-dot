
// Append to crates/proteus-core/src/core/session_store/remote/view/tests.rs.
#[test]
fn r7_latest_named_tool_repairs_to_same_accepted_call_after_rediscovery() {
    use proteus_contracts::app_protocol::AppTranscriptTool;
    let (backend, store) = Backend::store();
    backend.append(55);
    let mut model = SessionReadModel::from_validated(
        &store,
        RemoteValidatedRead::open(store.clone()).unwrap(),
        full,
    ).unwrap();
    for (index, call, status) in [(0, "earlier", "completed"),
                                  (50, "later", "completed"),
                                  (53, "failed", "failed"),
                                  (54, "denied", "denied")] {
        model.transcript[index].tool = Some(AppTranscriptTool {
            terminal: None, call_id: call.into(), name: "edit".into(),
            args: serde_json::json!({"original":call}),
            effective_args: Some(serde_json::json!({"effective":call})),
            status: status.into(), result: None, metadata: serde_json::Value::Null,
        });
    }
    let source = RemoteCacheSource::read(&store).unwrap();
    store.save_read_model(&source, &model);
    let first = store.saved_tool_state("edit").unwrap();
    let expected = first.tool.as_ref().unwrap();
    assert_eq!(expected.call_id, "later");
    assert_eq!(expected.args["original"], "later");
    assert_eq!(expected.effective_args.as_ref().unwrap()["effective"], "later");
    let header = cache::header(&store).unwrap();
    assert!(header.transcript.pages.len() > 1);
    let key = format!("display-data-{}", header.tools["edit"]);
    let reads = backend.0.lock().unwrap().record_reads;
    // Invalid derived value, not corrupt canonical data.
    backend.0.lock().unwrap().cache.insert(key.clone(), serde_json::json!({"unrelated":true}));
    let repaired = store.saved_tool_state("edit").unwrap();
    assert_eq!(serde_json::to_value(repaired).unwrap(), serde_json::to_value(&first).unwrap());
    assert_eq!(backend.0.lock().unwrap().record_reads, reads);
    // If a prerequisite page is lost too, a partial scan may not publish a guess.
    let page_key = format!("display-data-{}",header.transcript.pages.last().unwrap().hash);
    let page = {
        let mut state = backend.0.lock().unwrap();
        state.cache.remove(&key).unwrap();
        state.cache.remove(&page_key).unwrap()
    };
    assert!(store.saved_tool_state("edit").is_none());
    backend.0.lock().unwrap().cache.insert(page_key, page);
    let repaired = store.saved_tool_state("edit").unwrap();
    assert_eq!(serde_json::to_value(repaired).unwrap(), serde_json::to_value(&first).unwrap());
    // A new revision makes the entire saved index provisional.
    backend.append(1);
    assert!(store.saved_tool_state("edit").is_none());
}
