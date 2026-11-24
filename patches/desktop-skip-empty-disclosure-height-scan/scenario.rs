pub(super) fn run(flow: Flow, flags: u8) -> (Vec<Call>, usize) {
    use serde_json::json;
    use Flow::*;
    let mut this = Chat::default();
    let mut cx = Context::default();
    if flow == Empty {
        let (_, changes) = this.history.apply(&mut this.session.transcript, vec![], None);
        this.apply_history_changes(changes, &mut cx);
        return (cx.calls, this.visits.get());
    }
    let (_, first_changes) = this.history.apply(
        &mut this.session.transcript,
        fixture::rows(950, 1000),
        Some(fixture::cursor("first", 950)),
    );
    if flow == First {
        this.apply_history_changes(first_changes, &mut cx);
        return (cx.calls, this.visits.get());
    }
    this.apply_history_changes(first_changes, &mut cx);
    let accepted = |this: &mut Chat, end: usize| {
        let requested = this.history.request(Direction::Older, &this.session.transcript).unwrap();
        assert_eq!(requested.before, end);
        let mut page = fixture::page(end - 50, end);
        if end == 800 {
            let tool = |id: usize, metadata, terminal| AppTranscriptTool {
                terminal,
                call_id: format!("call-{id}"),
                name: "tool".into(),
                args: json!({}),
                effective_args: None,
                status: "done".into(),
                result: None,
                metadata,
            };
            for i in [2, 3, 4, 5, 6, 7, 8, 9, 10] {
                page.messages[i].message_id = None;
                page.messages[i].role = "system".into();
                page.messages[i].tool = Some(match i {
                    5 => tool(i, json!({}), Some(crate::contracts::ToolTerminalRef { id: uuid::Uuid::from_u128(2), title: "native-terminal".into(), tty: true })),
                    10 => tool(i, json!({
                        "tool": "spawn_agent",
                        "child_thread_id": "child-01",
                        "subagent_session": {
                            "session_id": "00000000-0000-0000-0000-000000000001",
                            "session_dir": "/saved/child-01"
                        }
                    }), None),
                    _ => tool(i, json!({}), None),
                });
            }
            page.messages[13].subagent = Some(AppTranscriptSubagent {
                child_thread_id: "child-01".into(),
                session: Some(AppSubagentSession {
                    session_id: uuid::Uuid::from_u128(1),
                    session_dir: "/saved/child-01".into(),
                }),
                role: "worker".into(),
                description: None,
                status: "running".into(),
                iterations: None,
                tools: vec![],
            });
        }
        this.history.accept_page(
            &this.session.transcript, Direction::Older, &requested, page, 0..2,
        ).unwrap()
    };
    for end in [950, 900, 850] {
        let changes = accepted(&mut this, end);
        this.apply_history_changes(changes, &mut cx);
    }
    this.visits.set(0);
    cx.calls.clear();
    let fourth = accepted(&mut this, 800);
    if flow == Paging {
        this.apply_history_changes(fourth, &mut cx);
        return (cx.calls, this.visits.get());
    }
    this.apply_history_changes(fourth, &mut cx);
    cx.calls.clear();
    assert_eq!(this.visits.get(), 0);
    assert_eq!(
        this.history.range(&this.session.transcript),
        Some(HistoryRange { start: 750, rows: 200, total: 1000 }),
    );
    let entries = this.display_transcript().entries();
    let (row3, row5, row8, row10, row13, row20) =
        (entries[3].key, entries[5].key, entries[8].key,
         entries[10].key, entries[13].key, entries[20].key);
    if flags & 1 != 0 { this.expanded.insert(row3); }
    if flags & 2 != 0 { this.full_blocks.insert((row8, 0)); }
    if flags & 4 != 0 { this.full_blocks.insert((row20, 1)); }
    if flags & 8 != 0 { this.open_chains.insert(row10); }
    if flags & 16 != 0 { this.tool_diffs.insert(row5, PhantomData); }
    if flags & 32 != 0 { this.expanded.insert(u64::MAX); }
    if flags & 64 != 0 { this.full_blocks.insert((row3, 2)); }
    if flags & 128 != 0 { this.expanded.insert(row13); }
    if flow == EmptyCodex {
        this.codex = Some(Codex { archive: Some(Transcript::default()) });
    }
    let mut next = fixture::cursor("first", 950);
    let mut messages = fixture::rows(950, 1000);
    if flow != Unchanged {
        next.revision = "second".into();
        next.base = Some(AppTranscriptBase { revision: "first".into(), common_prefix: 950 });
        messages[0].text = "actual changed live suffix".into();
    }
    let (change, changes) = this.history.apply(&mut this.session.transcript, messages, Some(next));
    assert!(changes.is_empty(), "verified prefix kept the whole archive");
    assert_eq!(change == Change::None, flow == Unchanged);
    this.apply_history_changes(changes, &mut cx);
    (cx.calls, this.visits.get())
}
