use std::{
    collections::BTreeMap,
    sync::{
        Mutex,
        atomic::{AtomicUsize, Ordering},
    },
};

use proteus_example_json_contracts::{JsonContracts, RECEIPT_KEY, TOOL_NAME, config::*, sha256};
use proteus_module_sdk::{
    contracts::{
        contracts::{ExecutionAttribution, ProcessToolInvokeInput},
        domain::{ToolCall, ToolResult, new_execution_id},
        process_module::{ProcessModuleError, ToolModuleHost},
    },
    tool::ToolModule,
};
use serde_json::{Value, json};

type Mutation = Box<dyn Fn(&ToolCall, &mut ToolResult) + Send + Sync>;
struct Host {
    documents: BTreeMap<String, String>,
    calls: Mutex<Vec<ToolCall>>,
    mutate: Mutation,
    polls: AtomicUsize,
    cancel_at: usize,
    cancel_error: bool,
    callback_error: bool,
    raw_override: Option<String>,
    pad_response_to: Option<usize>,
}
impl Host {
    fn new(text: &str) -> Self {
        Self {
            documents: [("document.json".into(), text.into())].into(),
            calls: Mutex::new(vec![]),
            mutate: Box::new(|_, _| {}),
            polls: AtomicUsize::new(0),
            cancel_at: usize::MAX,
            cancel_error: false,
            callback_error: false,
            raw_override: None,
            pad_response_to: None,
        }
    }
}
impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        if self.cancel_error {
            return Err(ProcessModuleError::new("fixture cancellation query failed"));
        }
        Ok(self.polls.fetch_add(1, Ordering::SeqCst) + 1 >= self.cancel_at)
    }
    fn execute_tool_json(&self, input: String) -> Result<String, ProcessModuleError> {
        if self.callback_error {
            return Err(ProcessModuleError::new("fixture denied callback"));
        }
        let call: ToolCall = serde_json::from_str(&input).unwrap();
        assert_eq!(call.name, "read_file");
        assert_eq!(call.args.as_object().unwrap().len(), 1, "full reads only");
        self.calls.lock().unwrap().push(call.clone());
        if let Some(raw) = &self.raw_override {
            return Ok(raw.clone());
        }
        let path = call.args["path"].as_str().unwrap();
        let mut result = if let Some(text) = self.documents.get(path) {
            ToolResult::ok(call.id.clone(), text).with_metadata(json!({
                "tool":"read_file", "path":format!("/workspace/{path}"),
                "total_lines":text.lines().count(), "returned_lines":text.lines().count(), "truncated":false,
            }))
        } else {
            ToolResult::error(call.id.clone(), "fixture file absent")
        };
        (self.mutate)(&call, &mut result);
        let mut raw = serde_json::to_string(&result).unwrap();
        if let Some(size) = self.pad_response_to {
            raw.push_str(&" ".repeat(size.saturating_sub(raw.len())));
        }
        Ok(raw)
    }
}
fn config() -> Config {
    serde_json::from_value(json!({"schema_version":1,"suite_id":"suite","documents":[{"id":"doc","path":"document.json","assertions":[
        {"id":"version","pointer":"/version","rule":{"kind":"equals","expected":1}},
        {"id":"enabled","pointer":"/enabled","rule":{"kind":"equals","expected":false}}
    ]}]})).unwrap()
}
fn input() -> ProcessToolInvokeInput {
    ProcessToolInvokeInput {
        call: ToolCall::new("verify-1", TOOL_NAME, json!({})),
        cwd: "/workspace".into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: Default::default(),
    }
}
fn run(config: Config, host: &mut Host) -> anyhow::Result<ToolResult> {
    JsonContracts::new(config)?.invoke(input(), host)
}
fn assert_failed(result: ToolResult) {
    assert!(!result.ok, "{result:?}");
    assert!(result.error.is_some());
    assert!(result.metadata.get(RECEIPT_KEY).is_none());
}
const GOOD: &str = "{\"version\":1,\"enabled\":false}";

#[test]
fn actual_assertions_produce_byte_and_config_bound_receipt() {
    let policy = config();
    let config_hash = JsonContracts::new(policy.clone())
        .unwrap()
        .config_sha256()
        .to_owned();
    let mut host = Host::new(GOOD);
    let result = run(policy, &mut host).unwrap();
    assert!(result.ok);
    assert_eq!(result.call_id, "verify-1");
    assert_eq!(result.metadata[RECEIPT_KEY]["cwd"], "/workspace");
    let ids = result.metadata[RECEIPT_KEY]["documents"][0]["assertions_executed"]
        .as_array()
        .unwrap();
    assert_eq!(ids.len(), 2);
    for id in ids {
        assert!(id["check_id"].as_str().unwrap().contains(&config_hash));
        assert!(
            id["check_id"]
                .as_str()
                .unwrap()
                .contains(&sha256(GOOD.as_bytes()))
        );
    }
    assert_eq!(
        result.metadata[RECEIPT_KEY]["documents"][0]["reader_call_id"],
        host.calls.lock().unwrap()[0].id
    );
    assert_eq!(result.metadata[RECEIPT_KEY]["config_sha256"], config_hash);
    assert!(result.output.contains("not a code/test-suite result"));
}

#[test]
fn no_model_arguments_can_select_policy_paths_or_results() {
    let module = JsonContracts::new(config()).unwrap();
    for args in [
        json!({"passed":true}),
        json!({"path":"other.json"}),
        json!({"checks":[]}),
        Value::Null,
    ] {
        let mut request = input();
        request.call.args = args;
        let mut host = Host::new(GOOD);
        assert!(module.invoke(request, &mut host).is_err());
        assert!(host.calls.lock().unwrap().is_empty());
    }
}

#[test]
fn zero_checks_and_duplicate_or_ambiguous_mapping_are_config_errors() {
    let mut cases = vec![];
    let mut c = config();
    c.documents.clear();
    cases.push(c);
    let mut c = config();
    c.documents[0].assertions.clear();
    cases.push(c);
    let mut c = config();
    c.documents.push(c.documents[0].clone());
    cases.push(c);
    let mut c = config();
    let mut d = c.documents[0].clone();
    d.id = "other".into();
    c.documents.push(d);
    cases.push(c);
    let mut c = config();
    let a = c.documents[0].assertions[0].clone();
    c.documents[0].assertions.push(a);
    cases.push(c);
    for c in cases {
        assert!(JsonContracts::new(c).is_err());
    }
}

#[test]
fn missing_null_false_and_empty_values_are_not_confused() {
    let mut c = config();
    c.documents[0].assertions = vec![Assertion {
        id: "present".into(),
        pointer: "/x".into(),
        rule: Rule::Exists,
    }];
    for text in ["{\"x\":null}", "{\"x\":false}", "{\"x\":\"\"}"] {
        assert!(run(c.clone(), &mut Host::new(text)).unwrap().ok);
    }
    assert_failed(run(c, &mut Host::new("{}")).unwrap());
}

#[test]
fn mismatch_after_passing_check_has_no_partial_receipt() {
    assert_failed(run(config(), &mut Host::new("{\"version\":1,\"enabled\":true}")).unwrap());
}

#[test]
fn syntactically_valid_partial_or_redacted_data_never_passes() {
    for key in [
        "truncated",
        "output_truncated",
        "error_truncated",
        "canceled",
        "timed_out",
        "redacted",
    ] {
        let key = key.to_owned();
        let mut host = Host::new(GOOD);
        host.mutate = Box::new(move |_, result| {
            result.metadata[&key] = json!(true);
        });
        assert_failed(run(config(), &mut host).unwrap());
    }
}

#[test]
fn full_read_metadata_is_required_and_typed() {
    for key in ["tool", "path", "total_lines", "returned_lines", "truncated"] {
        let key = key.to_owned();
        let mut host = Host::new(GOOD);
        host.mutate = Box::new(move |_, r| {
            r.metadata.as_object_mut().unwrap().remove(&key);
        });
        assert_failed(run(config(), &mut host).unwrap());
    }
    for (key, value) in [
        ("truncated", json!("false")),
        ("returned_lines", json!(2)),
        ("total_lines", json!(0)),
        ("path", json!("/elsewhere/document.json")),
        ("tool", json!("shell")),
        ("duration_ms", json!(-1)),
        ("redacted", json!(false)),
    ] {
        let mut host = Host::new(GOOD);
        host.mutate = Box::new(move |_, r| r.metadata[key] = value.clone());
        assert_failed(run(config(), &mut host).unwrap());
    }
}

#[test]
fn core_duration_and_explicit_false_failure_flags_are_supported() {
    let mut host = Host::new(GOOD);
    host.mutate = Box::new(|_, r| {
        r.metadata["duration_ms"] = json!(5);
        r.metadata["output_truncated"] = json!(false);
    });
    assert!(run(config(), &mut host).unwrap().ok);
}

#[test]
fn successful_bytes_from_wrong_call_id_do_not_count() {
    let mut host = Host::new(GOOD);
    host.mutate = Box::new(|_, r| r.call_id = "unrelated".into());
    assert_failed(run(config(), &mut host).unwrap());
}

#[test]
fn reader_error_and_contradictory_ok_error_are_rejected() {
    for ok in [false, true] {
        let mut host = Host::new(GOOD);
        host.mutate = Box::new(move |_, r| {
            r.ok = ok;
            r.error = Some("fixture denied".into());
        });
        assert_failed(run(config(), &mut host).unwrap());
    }
}

#[test]
fn invalid_duplicate_trailing_and_overdeep_json_fail() {
    let deep = format!(
        "{{\"version\":1,\"enabled\":false,\"extra\":{}0{}}}",
        "[".repeat(MAX_DEPTH),
        "]".repeat(MAX_DEPTH)
    );
    for (text, diagnostic) in [
        ("{", "not unambiguous bounded JSON"),
        (
            "{\"version\":1,\"version\":1,\"enabled\":false}",
            "duplicate JSON object key",
        ),
        (
            "{\"version\":1,\"enabled\":false} {}",
            "trailing characters",
        ),
        ("{\"version\":NaN}", "not unambiguous bounded JSON"),
        (deep.as_str(), "JSON nesting limit exceeded"),
    ] {
        let result = run(config(), &mut Host::new(text)).unwrap();
        assert!(
            result.error.as_deref().unwrap().contains(diagnostic),
            "{result:?}"
        );
        assert_failed(result);
    }
}

#[test]
fn cancellation_at_every_poll_including_last_never_returns_receipt() {
    let mut baseline = Host::new(GOOD);
    assert!(run(config(), &mut baseline).unwrap().ok);
    let count = baseline.polls.load(Ordering::SeqCst);
    assert!(count >= 7);
    for cancel_at in 1..=count {
        let mut host = Host::new(GOOD);
        host.cancel_at = cancel_at;
        assert!(
            run(config(), &mut host)
                .unwrap_err()
                .to_string()
                .contains("canceled"),
            "poll {cancel_at}"
        );
    }
}

#[test]
fn callback_failure_or_failed_cancellation_query_is_not_permission() {
    let mut host = Host::new(GOOD);
    host.callback_error = true;
    assert!(run(config(), &mut host).is_err());
    let mut host = Host::new(GOOD);
    host.cancel_error = true;
    assert!(run(config(), &mut host).is_err());
}

#[test]
fn malformed_or_oversized_callback_never_passes() {
    for raw in [
        "{}".into(),
        "invalid".into(),
        " ".repeat(MAX_CALLBACK_BYTES + 1),
    ] {
        let mut host = Host::new(GOOD);
        host.raw_override = Some(raw);
        assert_failed(run(config(), &mut host).unwrap());
    }
}

#[test]
fn exact_file_byte_limit_and_one_over() {
    let padded = format!("{GOOD}{}", " ".repeat(MAX_FILE_BYTES - GOOD.len()));
    assert!(run(config(), &mut Host::new(&padded)).unwrap().ok);
    assert_failed(run(config(), &mut Host::new(&(padded + " "))).unwrap());
}

#[test]
fn exact_total_byte_limit_and_one_over() {
    let text = format!("{GOOD}{}", " ".repeat(MAX_FILE_BYTES - GOOD.len()));
    let mut c = config();
    let original = c.documents[0].clone();
    c.documents.clear();
    let mut host = Host::new(&text);
    for i in 0..4 {
        let mut d = original.clone();
        d.id = format!("d{i}");
        d.path = format!("d{i}.json");
        host.documents.insert(d.path.clone(), text.clone());
        c.documents.push(d);
    }
    assert!(run(c.clone(), &mut host).unwrap().ok);
    let mut d = original;
    d.id = "extra".into();
    d.path = "extra.json".into();
    d.assertions = vec![Assertion {
        id: "root".into(),
        pointer: "".into(),
        rule: Rule::Exists,
    }];
    host.documents.insert(d.path.clone(), "0".into());
    c.documents.push(d);
    let result = run(c, &mut host).unwrap();
    assert!(
        result
            .error
            .as_deref()
            .unwrap()
            .contains("total document byte bound")
    );
    assert_failed(result);
}

#[test]
fn json_pointer_escaping_and_root_are_real_checks() {
    let mut c = config();
    c.documents[0].assertions = vec![
        Assertion {
            id: "root".into(),
            pointer: "".into(),
            rule: Rule::Type {
                expected: JsonType::Object,
            },
        },
        Assertion {
            id: "escaped".into(),
            pointer: "/a~1b/~0key/0".into(),
            rule: Rule::Equals { expected: json!(7) },
        },
        Assertion {
            id: "emptykey".into(),
            pointer: "/".into(),
            rule: Rule::Exists,
        },
    ];
    assert!(
        run(c, &mut Host::new("{\"a/b\":{\"~key\":[7]},\"\":null}"))
            .unwrap()
            .ok
    );
}

#[test]
fn invalid_pointers_paths_ids_and_unknown_config_fields_fail() {
    for pointer in ["x", "/~", "/~2", "/~01~"] {
        let mut c = config();
        c.documents[0].assertions[0].pointer = pointer.into();
        assert!(c.validate().is_err());
    }
    for path in ["/abs", "../x", "a/../x", "./x", "a//b", "a\\b", "C:x", ""] {
        let mut c = config();
        c.documents[0].path = path.into();
        assert!(c.validate().is_err());
    }
    for id in ["", "a:b", "a b", "é"] {
        let mut c = config();
        c.suite_id = id.into();
        assert!(c.validate().is_err());
    }
    let mut value = serde_json::to_value(config()).unwrap();
    value["skip"] = json!(true);
    assert!(serde_json::from_value::<Config>(value).is_err());
}

#[test]
fn exact_assertion_and_document_count_limits() {
    let mut c = config();
    let a = c.documents[0].assertions[0].clone();
    c.documents[0].assertions = (0..MAX_ASSERTIONS)
        .map(|i| {
            let mut a = a.clone();
            a.id = format!("a{i}");
            a
        })
        .collect();
    assert!(run(c.clone(), &mut Host::new(GOOD)).unwrap().ok);
    let mut extra = a;
    extra.id = "extra".into();
    c.documents[0].assertions.push(extra);
    assert!(c.validate().is_err());
    let mut c = config();
    let d = c.documents[0].clone();
    c.documents = (0..MAX_DOCUMENTS)
        .map(|i| {
            let mut d = d.clone();
            d.id = format!("d{i}");
            d.path = format!("d{i}.json");
            d
        })
        .collect();
    assert!(c.validate().is_ok());
    let mut extra = d;
    extra.id = "extra".into();
    extra.path = "extra.json".into();
    c.documents.push(extra);
    assert!(c.validate().is_err());
}

#[test]
fn content_and_policy_changes_produce_distinct_receipt_ids() {
    let ids = |result: &ToolResult| -> Vec<String> {
        result.metadata[RECEIPT_KEY]["documents"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|document| document["assertions_executed"].as_array().unwrap().iter())
            .map(|assertion| assertion["check_id"].as_str().unwrap().to_owned())
            .collect()
    };
    let first = run(config(), &mut Host::new(GOOD)).unwrap();
    let second = run(config(), &mut Host::new(&(GOOD.to_owned() + "\n"))).unwrap();
    assert_ne!(ids(&first), ids(&second));
    let mut c = config();
    c.suite_id = "different".into();
    let third = run(c, &mut Host::new(GOOD)).unwrap();
    assert_ne!(ids(&first), ids(&third));
}

#[test]
fn sha256_is_standard_not_an_authentication_claim() {
    assert_eq!(
        sha256(b""),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
    assert_eq!(
        sha256(b"abc"),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
}

#[test]
fn floating_point_rounding_cannot_create_equality_evidence() {
    for expected in [
        json!(9007199254740992.0),
        json!({"nested":[9007199254740992.0]}),
    ] {
        let mut c = config();
        c.documents[0].assertions[0].rule = Rule::Equals { expected };
        assert!(JsonContracts::new(c).is_err());
    }
    for text in [
        "{\"version\":1.0,\"enabled\":false}",
        "{\"version\":1e0,\"enabled\":false}",
        "{\"version\":9007199254740993.0,\"enabled\":false}",
    ] {
        assert_failed(run(config(), &mut Host::new(text)).unwrap());
    }
    let mut c = config();
    c.documents[0].assertions[0].rule = Rule::Equals {
        expected: json!(u64::MAX),
    };
    assert!(
        run(
            c,
            &mut Host::new("{\"version\":18446744073709551615,\"enabled\":false}")
        )
        .unwrap()
        .ok
    );
}

#[test]
fn callback_byte_limit_accepts_exact_and_rejects_one_more() {
    let mut host = Host::new(GOOD);
    host.pad_response_to = Some(MAX_CALLBACK_BYTES);
    assert!(run(config(), &mut host).unwrap().ok);
    let mut host = Host::new(GOOD);
    host.pad_response_to = Some(MAX_CALLBACK_BYTES + 1);
    let result = run(config(), &mut host).unwrap();
    assert!(
        result
            .error
            .as_deref()
            .unwrap()
            .contains("reader response exceeds")
    );
    assert_failed(result);
}

#[test]
fn exact_config_byte_limit_and_one_more() {
    let mut c = config();
    c.documents[0].assertions[0].rule = Rule::Equals {
        expected: json!(""),
    };
    let overhead = serde_json::to_vec(&c).unwrap().len();
    c.documents[0].assertions[0].rule = Rule::Equals {
        expected: json!("x".repeat(MAX_CONFIG_BYTES - overhead)),
    };
    assert_eq!(serde_json::to_vec(&c).unwrap().len(), MAX_CONFIG_BYTES);
    assert!(c.validate().is_ok());
    if let Rule::Equals { expected } = &mut c.documents[0].assertions[0].rule {
        *expected = json!(format!("{}x", expected.as_str().unwrap()));
    }
    assert!(
        c.validate()
            .unwrap_err()
            .to_string()
            .contains("config byte limit")
    );
}

#[test]
fn exact_depth_limit_accepts_before_one_more_rejects() {
    let text = format!(
        "{{\"version\":1,\"enabled\":false,\"extra\":{}0{}}}",
        "[".repeat(MAX_DEPTH - 1),
        "]".repeat(MAX_DEPTH - 1)
    );
    assert!(run(config(), &mut Host::new(&text)).unwrap().ok);
}

#[test]
fn non_empty_and_type_checks_have_explicit_not_truthy_semantics() {
    for (value, passes) in [
        (json!(""), false),
        (json!([]), false),
        (json!({}), false),
        (json!(true), false),
        (json!(0), false),
        (json!(" "), true),
        (json!([null]), true),
        (json!({"x":null}), true),
    ] {
        assert_eq!(Rule::NonEmpty.matches(Some(&value)), passes);
    }
    for (kind, value) in [
        (JsonType::Null, json!(null)),
        (JsonType::Boolean, json!(false)),
        (JsonType::Number, json!(1.5)),
        (JsonType::Integer, json!(1)),
        (JsonType::String, json!("")),
        (JsonType::Array, json!([])),
        (JsonType::Object, json!({})),
    ] {
        assert!(Rule::Type { expected: kind }.matches(Some(&value)));
        assert!(!Rule::Type { expected: kind }.matches(None));
    }
    assert!(
        !Rule::Type {
            expected: JsonType::Integer
        }
        .matches(Some(&json!(1.0)))
    );
}

#[test]
fn explicit_null_optional_metadata_is_ambiguous_not_absent() {
    for key in [
        "duration_ms",
        "canceled",
        "output_truncated",
        "error_truncated",
        "timed_out",
    ] {
        let mut host = Host::new(GOOD);
        host.mutate = Box::new(move |_, result| result.metadata[key] = Value::Null);
        assert_failed(run(config(), &mut host).unwrap());
    }
}
