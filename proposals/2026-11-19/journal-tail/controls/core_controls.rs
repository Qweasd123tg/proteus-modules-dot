fn r8_full(source: &mut RemoteJournalSnapshot) -> Result<Vec<AppTranscriptMessage>> {
    crate::app_server::journal_transcript_from_source(source, None)
}
fn r8_stable_model(store: &RemoteSessionStore) {
    let got = serde_json::to_value(store.fresh_read_model().expect("published model")).unwrap();
    let expected = SessionReadModel::from_validated(store, RemoteValidatedRead::open(store.clone()).unwrap(), r8_full).unwrap();
    assert_eq!(got, serde_json::to_value(expected).unwrap());
}
fn r8_size_suffix(state: &mut support::State, from: usize, target: usize) {
    let used: usize = state.records[from..].iter().map(|r| serde_json::to_vec(r).unwrap().len()).sum();
    use crate::core::JournalEntry;
    use crate::model_standard::ContentPart;
    let JournalEntry::HistoryMutated(m) = &mut state.records.last_mut().unwrap().entry else {unreachable!()};
    let ContentPart::Text{text} = &mut m.messages[0].parts[0].payload else {unreachable!()};
    text.push_str(&"y".repeat(target.checked_sub(used).unwrap()));
    assert_eq!(target, state.records[from..].iter().map(|r| serde_json::to_vec(r).unwrap().len()).sum::<usize>());
}
#[test]
fn r8_qualified_record_and_byte_limits_match_full_model() {
    // The 7-record prefix places the suffix inside a normal 64-record RPC page;
    // cap=3 additionally exercises short non-terminal pages.
    for (n,size) in [(1,0),(16,0),(17,0),(65,0),(3,262143),(3,262144),(3,262145),(1,280000)] {
        let (backend,store)=Backend::store();
        backend.0.lock().unwrap().r8_page_cap=3;
        for _ in 0..7 {backend.append(1);}
        project(&store,r8_full).unwrap();
        for _ in 0..n {backend.append(1);}
        if size>0 {r8_size_suffix(&mut backend.0.lock().unwrap(),7,size);}
        let view=project(&store,|_|panic!("independent append unnecessarily went to complete projection: {n},{size}")).unwrap();
        assert_eq!(view.summary.message_count,7+n);
        assert_eq!(view.cursor.unwrap().base.unwrap().common_prefix,7);
        r8_stable_model(&store);
    }
}
#[test]
fn r8_error_on_a_late_capped_page_preserves_published_head_and_retries() {
    // Both short retained suffix and long streaming suffix must finish validating
    // all pages before the published pointer is changed.
    for (n, oversized, wrong_descriptor) in [(14,false,false),(30,false,false),(14,true,false),(14,false,true)] {
        let (backend,store)=Backend::store();
        backend.0.lock().unwrap().r8_page_cap=2;
        backend.append(1);backend.append(1);
        project(&store,r8_full).unwrap();
        let before=backend.0.lock().unwrap().cache["display-view-v1-head"].clone();
        for _ in 0..n {backend.append(1);}
        if oversized {r8_size_suffix(&mut backend.0.lock().unwrap(),2,300000);}
        {
            let mut s=backend.0.lock().unwrap(); s.writes.clear();
            if wrong_descriptor {s.r8_wrong_snapshot_at=Some(12);} else {s.fail_after_seq=Some(12);}
        }
        assert!(project(&store,r8_full).is_err());
        {
            let mut s=backend.0.lock().unwrap();
            assert_eq!(s.cache["display-view-v1-head"],before);
            assert!(!s.writes.iter().any(|k|k=="display-view-v1-head"));
            s.r8_wrong_snapshot_at=None;s.fail_after_seq=None;
        }
        assert_eq!(project(&store,r8_full).unwrap().summary.message_count,n+2);
        r8_stable_model(&store);
    }
}
#[test]
fn r8_source_advances_at_head_publication_no_relabelling() {
    let (backend,store)=Backend::store();
    backend.append(1);project(&store,r8_full).unwrap();
    let old=backend.0.lock().unwrap().cache["display-view-v1-head"].clone();
    backend.append(1);
    backend.0.lock().unwrap().r8_advance_at_publish=true;
    let v=project(&store,r8_full).unwrap();
    // Caller gets its verified snapshot, not a purportedly current newer revision.
    assert_eq!(v.summary.message_count,2);
    assert_eq!(v.transcript.len(),2);
    assert!(v.cursor.is_none());
    assert_eq!(backend.0.lock().unwrap().cache["display-view-v1-head"],old);
    assert!(store.fresh_read_model().is_none());
    assert_eq!(project(&store,r8_full).unwrap().summary.message_count,3);
    r8_stable_model(&store);
}
#[test]
fn r8_reset_inside_short_suffix_does_not_append_stale_rows() {
    let (backend,store)=Backend::store(); backend.append(1); backend.append(1);
    project(&store,r8_full).unwrap(); backend.append(1); backend.append(1);
    {
        let mut s=backend.0.lock().unwrap();
        let crate::core::JournalEntry::HistoryMutated(m)=&mut s.records[2].entry else{unreachable!()};
        m.mutation=crate::core::HistoryMutationKind::Replace;
    }
    let mut calls=0;
    let v=project(&store,|source|{calls+=1;r8_full(source)}).unwrap();
    assert!(calls>0,"reset must not use short suffix as an independent append");
    assert_eq!(v.transcript.len(),2);assert_eq!(v.summary.message_count,2);
    r8_stable_model(&store);
}
