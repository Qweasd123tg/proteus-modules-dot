
#[test]
#[ignore = "explicit release-mode benchmark or parity run only"]
fn round4_deferred_call_probe() {
    use std::{env, time::{Duration, Instant}};
    let case = env::var("PROTEUS_CASE").expect("PROTEUS_CASE");
    let repeats: usize = env::var("PROTEUS_REPEATS").unwrap_or_else(|_| "1".into()).parse().unwrap();
    let n = if case.ends_with("large") { 2048 } else { 1 };
    let text = "A plain line with a quoted \"key\", split\nover two lines. Привет!\n".repeat(n);
    let args = json!({"path":"notes.txt","content":text});
    let outer = json!({"name":"fixture_write","args":args});
    let raw = serde_json::to_string(&outer).unwrap();
    let spec = ToolSpec::new("fixture_write", "Write the supplied content to a fixture", json!({
        "type": "object","properties":{"path":{"type":"string"},"content":{"type":"string"}},
        "required":["path","content"]
    }), ToolSafety::WritesFiles);
    let input = workflow_input("write the fixture using the hidden tool");
    let input_json = serde_json::to_string(&input).unwrap();
    let id = new_call_id();
    let mut call = ToolCall::new(id.clone(), dynamic_tools::TOOL_CALL, outer.clone());
    let mut phase = "execute";
    let expected_error = match case.as_str() {
        "invalid" => {
            call = call.with_raw_arguments("{");
            Some("failed to parse function arguments")
        }
        "schema" => {
            call = call.with_raw_arguments(r#"{"name":9,"args":{}}"#);
            Some("arguments violate schema")
        }
        "plan" => {
            phase = "plan";
            call = call.with_raw_arguments(&raw);
            Some("workflow tool is unavailable in this phase")
        }
        "recursive" => {
            call = call.with_raw_arguments(r#"{"name":"proteus_tool_search","args":{}}"#);
            Some("cannot call Proteus meta-tools")
        }
        "hidden" => {
            call = call.with_raw_arguments(r#"{"name":"unavailable","args":{}}"#);
            Some("not available or is denied by policy")
        }
        "describe" => {
            call = ToolCall::new(id.clone(), dynamic_tools::TOOL_DESCRIBE, json!({"name":"fixture_write"}))
                .with_raw_arguments(r#"{"name":"fixture_write"}"#);
            None
        }
        "noraw" => None,
        "authority" => {
            call.args = json!({"name":"not_the_tool","args":{"other":"value"}});
            call = call.with_raw_arguments(&raw);
            None
        }
        "small" | "large" | "workflow-small" | "workflow-large" => {
            call = call.with_raw_arguments(&raw);
            None
        }
        _ => panic!("unknown case"),
    };
    let mut nanos = Duration::ZERO;
    let mut snapshot = Value::Null;
    // Exclude one whole dispatch in each fresh process from the sample.
    for step in 0..=repeats {
        let mut host = if case.starts_with("workflow-") {
            FakeHost::with_responses(vec![
                tool_call_response(call.clone()),
                CanonicalModelResponse::new(CanonicalMessage::text(MessageRole::Assistant, "final"),
                    Vec::new(), FinishReason::Stop),
            ])
        } else {
            FakeHost::default()
        }.with_tools(vec![spec.clone()], Vec::new());
        let result = if case.starts_with("workflow-") {
            let request = input_json.clone();
            let start = Instant::now();
            let response = CodingSingleLoopWorkflow::default().run_json(request, &mut host).unwrap();
            let elapsed = start.elapsed();
            if step != 0 { nanos += elapsed; }
            let response: WorkflowModuleOutput = serde_json::from_str(response.as_str()).unwrap();
            let result = response.new_messages.iter().flat_map(|m| &m.parts).find_map(|p| {
                match &p.payload {
                    ContentPart::ToolResult { result } => Some(result.clone()),
                    _ => None,
                }
            }).unwrap();
            let checkpoints = host.checkpoints.lock().unwrap();
            assert_eq!(checkpoints[0].tool_results[0].execution_call, host.executed_calls.lock().unwrap()[0]);
            result
        } else {
            let start = Instant::now();
            let result = dynamic_tools::handle_meta_tool_call(&mut host, &input, &call, phase).unwrap();
            let elapsed = start.elapsed();
            if step != 0 { nanos += elapsed; }
            result
        };
        assert_eq!(result.call_id, id);
        let calls = host.executed_calls.lock().unwrap();
        if let Some(message) = expected_error {
            assert!(!result.ok);
            assert!(result.error.as_ref().unwrap().contains(message), "{result:?}");
            assert!(calls.is_empty());
            if case == "invalid" || case == "schema" {
                assert_eq!(result.metadata["validation_error"], true);
            }
        } else if case == "describe" {
            assert!(result.ok);
            assert_eq!(serde_json::from_str::<Value>(&result.output).unwrap()["name"], "fixture_write");
            assert!(calls.is_empty());
        } else {
            assert!(result.ok);
            assert_eq!(result.output, "fixture_write ok");
            assert_eq!(result.metadata, json!({"inner":true}));
            assert_eq!(calls.as_slice(), &[ToolCall::new(id.clone(), "fixture_write", args.clone())]);
        }
        // Compare the complete result across builds, normalizing the fresh ID only.
        let mut value = serde_json::to_value(result).unwrap();
        value["call_id"] = json!("fixed");
        snapshot = value;
    }
    println!("PROBE {}", json!({"case":case, "raw_bytes":call.raw_arguments.as_ref().map_or(0, |s| s.len()),
        "iters":repeats, "ns":nanos.as_nanos() as u64, "result":snapshot}));
}
