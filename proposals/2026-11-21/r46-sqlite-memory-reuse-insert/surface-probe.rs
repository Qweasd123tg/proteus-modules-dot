use super::*;
use proteus_contracts::{
    contracts::{ExecutionAttribution, ProcessContextProviderInput, ProcessContextProviderRequest},
    domain::{AgentTask, ContextChunk, ToolCall, new_execution_id},
    process_module::{
        ContextProviderModule, ToolModule, ToolModuleHost, ToolModuleInvocationContext,
    },
};
use serde_json::json;

struct Host;

impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
}

fn invoke(store: &Arc<SqliteMemoryStore>, name: &str, args: Value) -> Value {
    let tool = tools::MemoryTool {
        store: store.clone(),
        remember: name == "remember_fact",
    };
    let context = ToolModuleInvocationContext {
        cwd: ".".into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: Default::default(),
        config: json!({}),
    };
    let response = tool
        .invoke_json(
            serde_json::to_string(&ToolCall::new("memory_test", name, args)).unwrap(),
            serde_json::to_string(&context).unwrap(),
            &mut Host,
        )
        .unwrap();
    serde_json::from_str(&response).unwrap()
}

fn provide(store: &Arc<SqliteMemoryStore>, text: &str, limit: usize) -> Vec<ContextChunk> {
    let provider = provider::MemoryProvider {
        store: store.clone(),
    };
    let request = ProcessContextProviderRequest {
        input: ProcessContextProviderInput {
            provider_id: "sqlite_memory".into(),
            task: AgentTask::new("remember preferences", ".".into()),
            metadata: json!({"text": text, "limit": limit}),
        },
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: Default::default(),
    };
    serde_json::from_str(
        &provider
            .provide_json(serde_json::to_string(&request).unwrap())
            .unwrap(),
    )
    .unwrap()
}

#[test]
fn repeated_surface_calls_use_current_bindings_and_keep_metadata() {
    let store = Arc::new(SqliteMemoryStore { conn: fresh_conn() });
    let content = "предпочтение💡\r\nRust \"память\"";
    let metadata = json!({"nested": [{"unicode": "ёж", "nil": null, "n": 7}], "bool": true});
    assert_eq!(
        invoke(
            &store,
            "remember_fact",
            json!({
                "kind":"preference", "content":content, "metadata":metadata
            })
        )["ok"],
        true
    );
    assert_eq!(
        invoke(
            &store,
            "remember_fact",
            json!({
                "kind":"fact", "content":"other language"
            })
        )["ok"],
        true
    );

    let tool = invoke(&store, "recall_memory", json!({"query":"Rust", "limit":1}));
    assert_eq!(tool["ok"], true);
    assert_eq!(tool["output"], format!("preference: {content}"));
    let item = json!({"kind":"preference", "content":content, "metadata":metadata});
    assert_eq!(tool["metadata"]["items"], json!([item.clone()]));
    assert_eq!(
        provide(&store, "Rust", 1),
        [ContextChunk::new("memory:preference", content).with_metadata(metadata)]
    );

    assert_eq!(
        provide(&store, "other", 2),
        [ContextChunk::new("memory:fact", "other language")]
    );
    let none = invoke(
        &store,
        "recall_memory",
        json!({"query":"missing", "limit":2}),
    );
    assert_eq!(none["output"], "(no memories)");
    assert_eq!(none["metadata"]["items"], json!([]));

    let recent = invoke(&store, "recall_memory", json!({"query":"", "limit":2}));
    assert_eq!(
        recent["metadata"]["items"],
        json!([
            {"kind":"fact", "content":"other language", "metadata":null},
            item
        ])
    );
    assert_eq!(provide(&store, "", 1)[0].content, "other language");
    for query in ["", "Rust"] {
        assert_eq!(
            invoke(&store, "recall_memory", json!({"query":query, "limit":0}))["metadata"]["items"],
            json!([])
        );
        assert!(provide(&store, query, 0).is_empty());
    }
}

// A row callback error must not leave the cached cursor or old bindings active.
#[test]
fn detects_corrupt_metadata_then_reuses_statement_after_repair() {
    let conn = fresh_conn();
    remember_impl(&conn, r#"{"kind":"fact","content":"Rust","metadata":null}"#).unwrap();
    remember_impl(
        &conn,
        r#"{"kind":"fact","content":"SQLite","metadata":null}"#,
    )
    .unwrap();
    let rust = r#"{"text":"Rust","limit":1}"#;
    let sqlite = r#"{"text":"SQLite","limit":2}"#;
    for (query, content) in [(rust, "Rust"), (sqlite, "SQLite")] {
        assert_eq!(
            serde_json::from_str::<Value>(&recall_impl(&conn, query).unwrap()).unwrap()[0]["content"],
            content
        );
    }
    conn.lock()
        .unwrap()
        .execute(
            "UPDATE memory_items SET metadata = 'broken-json' WHERE content = 'Rust'",
            [],
        )
        .unwrap();
    assert!(
        recall_impl(&conn, rust)
            .unwrap_err()
            .to_string()
            .contains("Conversion error")
    );
    let hits: Value = serde_json::from_str(&recall_impl(&conn, sqlite).unwrap()).unwrap();
    assert_eq!(
        hits,
        json!([{"kind":"fact","content":"SQLite","metadata":null}])
    );
    conn.lock()
        .unwrap()
        .execute(
            "UPDATE memory_items SET metadata = '{\"repaired\":true}' WHERE content = 'Rust'",
            [],
        )
        .unwrap();
    let fixed: Value = serde_json::from_str(&recall_impl(&conn, rust).unwrap()).unwrap();
    assert_eq!(fixed[0]["metadata"], json!({"repaired":true}));
}

#[test]
fn warmed_connection_observes_external_commits_in_wal_and_on_reopen() {
    struct Scratch(PathBuf);
    impl Drop for Scratch {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    let scratch = Scratch(std::env::temp_dir().join(format!("r46-sqlite-{}", new_execution_id())));
    std::fs::create_dir(&scratch.0).unwrap();
    let path = scratch.0.join("memory.sqlite");
    let store = Arc::new(SqliteMemoryStore::open(path.clone()).unwrap());
    invoke(
        &store,
        "remember_fact",
        json!({"kind":"fact","content":"before commit"}),
    );
    let outside = Connection::open(&path).unwrap();
    let mode: String = outside
        .query_row("PRAGMA journal_mode=WAL", [], |r| r.get(0))
        .unwrap();
    assert_eq!(mode, "wal");
    assert_eq!(provide(&store, "", 1)[0].content, "before commit");
    assert_eq!(provide(&store, "before", 1)[0].content, "before commit");
    outside
        .execute(
            "INSERT INTO memory_items (kind, content, metadata, created_at) VALUES
         ('preference', 'after commit', '{\"n\":2}', 123)",
            [],
        )
        .unwrap();
    let chunks =
        [ContextChunk::new("memory:preference", "after commit").with_metadata(json!({"n":2}))];
    assert_eq!(provide(&store, "", 1), chunks);
    assert_eq!(provide(&store, "after", 1), chunks);
    drop(store);
    drop(outside);
    let reopened = Arc::new(SqliteMemoryStore::open(path).unwrap());
    assert_eq!(provide(&reopened, "after", 1), chunks);
}

#[test]
fn externally_seeded_nesting_limit_is_unchanged() {
    let store = SqliteMemoryStore { conn: fresh_conn() };
    let nested = format!("{}0{}", "[".repeat(126), "]".repeat(126));
    assert!(serde_json::from_str::<Value>(&nested).is_ok());
    store
        .conn
        .lock()
        .unwrap()
        .execute(
            "INSERT INTO memory_items(kind, content, metadata, created_at)
         VALUES ('fact','depthguard',?1,0)",
            [nested],
        )
        .unwrap();
    for text in ["", "depthguard"] {
        let err = store.recall(&MemoryQuery::new(text, 1)).unwrap_err();
        assert!(err.message.contains("recursion limit"), "{}", err.message);
        assert!(store.recall(&MemoryQuery::new(text, 0)).unwrap().is_empty());
    }
}
