//! Authored boundary fixtures. This is a synthetic host, not a Core filesystem run.
use std::sync::{
    Mutex,
    atomic::{AtomicUsize, Ordering},
};

use proteus_example_evidence_spans::{
    EVIDENCE_KEY, EvidenceSpans, MODULE_ID, TOOL_NAME,
    config::{Config, MAX_CALLBACK_BYTES, MAX_FILE_BYTES, MAX_RESULT_BYTES},
    sha256,
};
use proteus_module_sdk::{
    contracts::{
        contracts::{
            ExecutionAttribution, ProcessComponentExportInitialize, ProcessModuleComposition,
            ProcessToolInvokeInput,
        },
        domain::{ToolCall, ToolContent, ToolResult, ToolSafety, new_execution_id},
        process_module::{ProcessModuleError, ToolModuleHost},
    },
    tool::ToolModule,
};
use serde_json::{Value, json};

type Mutation = Box<dyn Fn(&ToolCall, &mut ToolResult) + Send + Sync>;
struct Host {
    text: String,
    calls: Mutex<Vec<ToolCall>>,
    mutation: Mutation,
    polls: AtomicUsize,
    cancel_at: usize,
    cancel_error: bool,
    callback_error: bool,
    raw_override: Option<String>,
    raw_pad: Option<usize>,
    cwd: String,
}
impl Host {
    fn new(text: &str) -> Self {
        Self {
            text: text.into(),
            calls: Mutex::new(vec![]),
            mutation: Box::new(|_, _| {}),
            polls: AtomicUsize::new(0),
            cancel_at: usize::MAX,
            cancel_error: false,
            callback_error: false,
            raw_override: None,
            raw_pad: None,
            cwd: "/workspace".into(),
        }
    }
    fn count(&self) -> usize {
        self.calls.lock().unwrap().len()
    }
}
impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        if self.cancel_error {
            return Err(ProcessModuleError::new(
                "fixture cancel service unavailable",
            ));
        }
        Ok(self.polls.fetch_add(1, Ordering::SeqCst) + 1 >= self.cancel_at)
    }
    fn execute_tool_json(&self, raw: String) -> Result<String, ProcessModuleError> {
        let call: ToolCall = serde_json::from_str(&raw).unwrap();
        assert_eq!(call.name, "read_file");
        assert_eq!(
            call.args.as_object().unwrap().len(),
            1,
            "no range/reader options"
        );
        self.calls.lock().unwrap().push(call.clone());
        if self.callback_error {
            return Err(ProcessModuleError::new("fixture policy denied"));
        }
        if let Some(raw) = &self.raw_override {
            return Ok(raw.clone());
        }
        let path = call.args["path"].as_str().unwrap();
        let mut result=ToolResult::ok(call.id.clone(),self.text.clone()).with_metadata(json!({
            "tool":"read_file","path":format!("{}/{path}",self.cwd),
            "total_lines":self.text.lines().count(),"returned_lines":self.text.lines().count(),"truncated":false
        }));
        (self.mutation)(&call, &mut result);
        let mut raw = serde_json::to_string(&result).unwrap();
        if let Some(size) = self.raw_pad {
            raw.push_str(&" ".repeat(size.saturating_sub(raw.len())));
        }
        Ok(raw)
    }
}
const TEXT: &str = include_str!("../fixtures/source.txt");
fn config() -> Config {
    serde_json::from_value(
        json!({"schema_version":1,"sources":[{"id":"artifact","path":"source.txt"}]}),
    )
    .unwrap()
}
fn claim(id: &str, start: u64, end: u64, quote: &str) -> Value {
    json!({"claim_id":id,"start_byte":start,"end_byte":end,"quote":quote})
}
fn args(text: &str) -> Value {
    json!({"source_id":"artifact","expected_sha256":sha256(text.as_bytes()),"claims":[claim("first",0,5,"alpha")]})
}
fn input(args: Value) -> ProcessToolInvokeInput {
    ProcessToolInvokeInput {
        call: ToolCall::new("verify-1", TOOL_NAME, args),
        cwd: "/workspace".into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: Default::default(),
    }
}
fn run(args: Value, host: &mut Host) -> anyhow::Result<ToolResult> {
    EvidenceSpans::new(config())
        .unwrap()
        .invoke(input(args), host)
}
fn failed(result: ToolResult, contains: &str) {
    assert!(!result.ok, "unexpected success: {result:?}");
    assert!(
        result.error.as_deref().unwrap_or("").contains(contains),
        "{result:?}"
    );
    assert!(result.metadata.get(EVIDENCE_KEY).is_none());
    assert!(
        result
            .metadata
            .get("proteus.example.verification")
            .is_none()
    );
}
fn before_read(args: Value, contains: &str) {
    let mut host = Host::new(TEXT);
    failed(run(args, &mut host).unwrap(), contains);
    assert_eq!(host.count(), 0);
}

#[test]
fn exact_multibyte_and_ascii_witness_has_full_binding() {
    let mut host = Host::new(TEXT);
    let mut request = args(TEXT);
    request["claims"] = json!([
        claim("greeting", 6, 23, "Привет 🌍"),
        claim("accent", 24, 27, "é")
    ]);
    let module = EvidenceSpans::new(config()).unwrap();
    let result = module.invoke(input(request), &mut host).unwrap();
    assert!(result.ok);
    assert_eq!(host.count(), 1);
    let e = &result.metadata[EVIDENCE_KEY];
    assert_eq!(e["source_id"], "artifact");
    assert_eq!(e["configured_path"], "source.txt");
    assert_eq!(e["observed_path"], "/workspace/source.txt");
    assert_eq!(e["config_sha256"], module.config_sha256());
    assert_eq!(e["content_sha256"], sha256(TEXT.as_bytes()));
    assert_eq!(e["source_bytes"], 40);
    assert_eq!(e["verifier_call_id"], "verify-1");
    assert_eq!(e["reader_call_id"], host.calls.lock().unwrap()[0].id);
    assert_eq!(
        e["verified_claims"][0]["quote_sha256"],
        sha256("Привет 🌍".as_bytes())
    );
    assert_eq!(e["origin_verified"], false);
    assert_eq!(e["semantic_entailment"], "not_evaluated");
    assert_eq!(e["scope"], "observed_host_read_bytes");
    assert!(
        result
            .metadata
            .get("proteus.example.verification")
            .is_none()
    );
    assert!(!serde_json::to_string(&e).unwrap().contains("Привет"));
    assert!(serde_json::to_vec(&result).unwrap().len() <= MAX_RESULT_BYTES);
}

#[test]
fn same_bytes_under_different_operator_origin_have_different_binding() {
    let a = EvidenceSpans::new(config()).unwrap();
    let mut other = config();
    other.sources[0].path = "other.txt".into();
    let b = EvidenceSpans::new(other).unwrap();
    assert_ne!(a.config_sha256(), b.config_sha256());
    let mut host = Host::new(TEXT);
    let result = b.invoke(input(args(TEXT)), &mut host).unwrap();
    assert!(result.ok);
    assert_eq!(
        result.metadata[EVIDENCE_KEY]["configured_path"],
        "other.txt"
    );
    assert_eq!(
        result.metadata[EVIDENCE_KEY]["observed_path"],
        "/workspace/other.txt"
    );
}

#[test]
fn wrong_digest_is_not_repaired_by_quote_search() {
    let mut request = args(TEXT);
    request["expected_sha256"] = json!("0".repeat(64));
    let mut host = Host::new(TEXT);
    failed(run(request, &mut host).unwrap(), "SHA256 mismatch");
    assert_eq!(host.count(), 1);
}

#[test]
fn changed_source_with_old_digest_is_stale() {
    let mut host = Host::new(&TEXT.replace("omega", "theta"));
    failed(run(args(TEXT), &mut host).unwrap(), "SHA256 mismatch");
}

#[test]
fn valid_utf8_buffer_rejects_split_start_and_end() {
    for (start, end, quote) in [(7, 9, "xx"), (6, 7, "x"), (19, 22, "xxx")] {
        let mut request = args(TEXT);
        request["claims"] = json!([claim("split", start, end, quote)]);
        let mut host = Host::new(TEXT);
        failed(run(request, &mut host).unwrap(), "UTF-8 code point");
        assert_eq!(host.count(), 1);
    }
}

#[test]
fn same_length_wrong_quote_fails() {
    let mut request = args(TEXT);
    request["claims"] = json!([claim("wrong", 0, 5, "ALPHA")]);
    let mut host = Host::new(TEXT);
    failed(run(request, &mut host).unwrap(), "exactly match");
}

#[test]
fn all_claims_required_no_partial_positive_witness() {
    let mut request = args(TEXT);
    request["claims"] = json!([claim("good", 0, 5, "alpha"), claim("bad", 34, 39, "OMEGA")]);
    let mut host = Host::new(TEXT);
    failed(run(request, &mut host).unwrap(), "exactly match");
    assert_eq!(host.count(), 1);
}

#[test]
fn quote_not_normalized_unicode_or_line_endings() {
    let mut request = args(TEXT);
    request["claims"] = json!([claim("nfc", 24, 27, "éx")]);
    let mut host = Host::new(TEXT);
    failed(run(request, &mut host).unwrap(), "exactly match");
    let source = "a\r\nb";
    let mut request = args(source);
    request["claims"] = json!([claim("newline", 0, 4, "a\nxb")]);
    let mut host = Host::new(source);
    failed(run(request, &mut host).unwrap(), "exactly match");
    let mut request = args(source);
    request["claims"] = json!([claim("exact", 0, 4, source)]);
    assert!(run(request, &mut Host::new(source)).unwrap().ok);
}

#[test]
fn missing_quote_is_not_found_elsewhere() {
    let mut request = args(TEXT);
    request["claims"] = json!([claim("position", 34, 39, "alpha")]);
    failed(run(request, &mut Host::new(TEXT)).unwrap(), "exactly match");
}

#[test]
fn span_bounds_and_length_rejected() {
    for (start, end, quote, message) in [
        (0, 0, "", "nonempty"),
        (10, 2, "x", "nonempty"),
        (0, 6, "alpha", "length"),
        (65535, 65537, "xx", "offset"),
    ] {
        let mut request = args(TEXT);
        request["claims"] = json!([claim("bad", start, end, quote)]);
        before_read(request, message);
    }
    let mut request = args(TEXT);
    request["claims"] = json!([claim("past", 40, 41, "x")]);
    failed(
        run(request, &mut Host::new(TEXT)).unwrap(),
        "exceeds observed",
    );
}

#[test]
fn offsets_must_be_unsigned_integer_and_bounded() {
    for v in [
        json!(-1),
        json!(1.5),
        json!("0"),
        json!(null),
        json!(u64::MAX),
    ] {
        let mut request = args(TEXT);
        request["claims"][0]["start_byte"] = v;
        let mut host = Host::new(TEXT);
        assert!(!run(request, &mut host).unwrap().ok);
        assert_eq!(host.count(), 0);
    }
}

#[test]
fn duplicate_ids_and_empty_claims_fail_before_read() {
    let mut request = args(TEXT);
    request["claims"] = json!([claim("same", 0, 5, "alpha"), claim("same", 0, 5, "alpha")]);
    before_read(request, "duplicate");
    let mut request = args(TEXT);
    request["claims"] = json!([]);
    before_read(request, "claim count");
}

#[test]
fn unknown_source_path_and_extra_fields_never_dispatch() {
    let mut request = args(TEXT);
    request["source_id"] = json!("unknown");
    before_read(request, "operator-configured");
    let mut request = args(TEXT);
    request["path"] = json!("/other");
    before_read(request, "invalid evidence request");
    let mut request = args(TEXT);
    request["claims"][0]["passed"] = json!(true);
    before_read(request, "invalid evidence request");
    let mut request = args(TEXT);
    request["source_id"] = json!("../artifact");
    before_read(request, "source_id");
}

#[test]
fn digest_syntax_is_strict() {
    for digest in [
        "a".repeat(63),
        "a".repeat(65),
        "F".repeat(64),
        "g".repeat(64),
    ] {
        let mut request = args(TEXT);
        request["expected_sha256"] = json!(digest);
        before_read(request, "lowercase hexadecimal");
    }
}

#[test]
fn quote_aggregate_exact_bound_and_plus_one() {
    let source = "x".repeat(4096);
    let mut request = args(&source);
    request["claims"] = json!(
        (0..4)
            .map(|i| claim(&format!("q{i}"), 0, 4096, &source))
            .collect::<Vec<_>>()
    );
    let mut host = Host::new(&source);
    assert!(run(request.clone(), &mut host).unwrap().ok);
    assert_eq!(host.count(), 1);
    request["claims"]
        .as_array_mut()
        .unwrap()
        .push(claim("plus", 0, 1, "x"));
    before_read(request, "aggregate quote");
}

#[test]
fn quote_limit_is_bytes_not_unicode_scalar_count() {
    let source = "é".repeat(2048);
    let mut request = args(&source);
    request["claims"] = json!([claim("q", 0, 4096, &source)]);
    assert!(run(request, &mut Host::new(&source)).unwrap().ok);
    let oversized = format!("{source}x");
    let mut request = args(&oversized);
    request["claims"] = json!([claim("q", 0, 4097, &oversized)]);
    before_read(request, "quote byte bound");
}

#[test]
fn claim_count_exact_limit_and_plus_one() {
    let mut request = args(TEXT);
    request["claims"] = json!(
        (0..32)
            .map(|i| claim(&format!("q{i}"), 0, 5, "alpha"))
            .collect::<Vec<_>>()
    );
    assert!(run(request.clone(), &mut Host::new(TEXT)).unwrap().ok);
    request["claims"]
        .as_array_mut()
        .unwrap()
        .push(claim("q32", 0, 5, "alpha"));
    before_read(request, "claim count");
}

#[test]
fn raw_request_budget_rejects_before_read() {
    let mut request = args(TEXT);
    request["claims"][0]["quote"] = json!("x".repeat(65536));
    before_read(request, "request byte bound");
}

#[test]
fn wrong_reader_call_path_and_tool_each_fail_with_valid_other_fields() {
    for (key, value, message) in [
        ("path", json!("/workspace/wrong.txt"), "reader path"),
        ("tool", json!("other_reader"), "reader identity"),
    ] {
        let mut host = Host::new(TEXT);
        host.mutation = Box::new(move |_, r| r.metadata[key] = value.clone());
        failed(run(args(TEXT), &mut host).unwrap(), message);
    }
    let mut host = Host::new(TEXT);
    host.mutation = Box::new(|_, r| r.call_id = "wrong".into());
    failed(run(args(TEXT), &mut host).unwrap(), "call_id mismatch");
}

#[test]
fn incomplete_reader_and_unknown_metadata_are_rejected() {
    for (key, value, message) in [
        ("truncated", json!(true), "partial content"),
        ("total_lines", json!(5), "line counts"),
        ("returned_lines", json!(3), "line counts"),
        ("redacted", json!(false), "unsupported"),
        ("start_line", json!(1), "unsupported"),
        ("line_numbers", json!(false), "unsupported"),
    ] {
        let mut host = Host::new(TEXT);
        host.mutation = Box::new(move |_, r| r.metadata[key] = value.clone());
        failed(run(args(TEXT), &mut host).unwrap(), message);
    }
}

#[test]
fn successful_reader_cannot_carry_error_or_structured_content() {
    let mut host = Host::new(TEXT);
    host.mutation = Box::new(|_, r| r.error = Some("contradiction".into()));
    failed(run(args(TEXT), &mut host).unwrap(), "did not succeed");
    let mut host = Host::new(TEXT);
    host.mutation = Box::new(|_, r| r.ok = false);
    failed(run(args(TEXT), &mut host).unwrap(), "did not succeed");
    let mut host = Host::new(TEXT);
    host.mutation = Box::new(|_, r| {
        r.content.push(ToolContent::Text {
            text: "extra".into(),
        })
    });
    failed(run(args(TEXT), &mut host).unwrap(), "structured content");
}

#[test]
fn reader_optional_flags_reject_true_null_and_wrong_type() {
    for field in [
        "output_truncated",
        "error_truncated",
        "canceled",
        "timed_out",
    ] {
        for value in [json!(true), json!(null), json!("false"), json!(0)] {
            let mut host = Host::new(TEXT);
            host.mutation = Box::new(move |_, r| r.metadata[field] = value.clone());
            assert!(!run(args(TEXT), &mut host).unwrap().ok, "{field}");
        }
    }
    for value in [json!(null), json!(-1), json!(1.2), json!("0")] {
        let mut host = Host::new(TEXT);
        host.mutation = Box::new(move |_, r| r.metadata["duration_ms"] = value.clone());
        failed(run(args(TEXT), &mut host).unwrap(), "unsupported");
    }
}

#[test]
fn exact_file_output_bound_and_plus_one() {
    let text = format!("alpha{}", "x".repeat(MAX_FILE_BYTES - 5));
    assert!(run(args(&text), &mut Host::new(&text)).unwrap().ok);
    let text = format!("{text}x");
    failed(
        run(args(&text), &mut Host::new(&text)).unwrap(),
        "output byte bound",
    );
}

#[test]
fn raw_callback_bound_checked_before_json_decode() {
    let mut host = Host::new(TEXT);
    host.raw_pad = Some(MAX_CALLBACK_BYTES);
    assert!(run(args(TEXT), &mut host).unwrap().ok);
    let mut host = Host::new(TEXT);
    host.raw_pad = Some(MAX_CALLBACK_BYTES + 1);
    failed(run(args(TEXT), &mut host).unwrap(), "response byte bound");
    let mut host = Host::new(TEXT);
    host.raw_override = Some("not-json".into());
    failed(
        run(args(TEXT), &mut host).unwrap(),
        "invalid reader ToolResult",
    );
}

#[test]
fn host_denial_never_falls_back_to_direct_read() {
    let mut host = Host::new(TEXT);
    host.callback_error = true;
    failed(run(args(TEXT), &mut host).unwrap(), "fixture policy denied");
    assert_eq!(host.count(), 1);
}

#[test]
fn cancel_checks_cover_before_callback_after_callback_and_final_success() {
    // One claim makes success polls: begin,pre-read,post-read,post-envelope,claim,post-claims,pre-success.
    for cancel_at in 1..=7 {
        let mut host = Host::new(TEXT);
        host.cancel_at = cancel_at;
        assert_eq!(
            run(args(TEXT), &mut host).unwrap_err().to_string(),
            "span verification canceled",
            "cancel_at={cancel_at}"
        );
        assert_eq!(host.count(), usize::from(cancel_at >= 3));
    }
    let mut host = Host::new(TEXT);
    host.cancel_error = true;
    assert_eq!(
        run(args(TEXT), &mut host).unwrap_err().to_string(),
        "fixture cancel service unavailable"
    );
    assert_eq!(host.count(), 0);
}

#[test]
fn invalid_config_and_cwd_rejected() {
    for path in [
        "",
        "/absolute",
        "../outside",
        "a/../b",
        "a/./b",
        "a//b",
        "a\\b",
        "C:drive",
        "a\nb",
    ] {
        let mut cfg = config();
        cfg.sources[0].path = path.into();
        assert!(EvidenceSpans::new(cfg).is_err(), "{path:?}");
    }
    let mut cfg = config();
    cfg.sources.push(cfg.sources[0].clone());
    assert!(EvidenceSpans::new(cfg).is_err());
    let mut cfg = config();
    cfg.schema_version = 2;
    assert!(EvidenceSpans::new(cfg).is_err());
    let mut cfg = config();
    cfg.sources.clear();
    assert!(EvidenceSpans::new(cfg).is_err());
    for cwd in [
        "relative",
        "/workspace/../other",
        "/workspace/./other",
        "/workspace//other",
    ] {
        let mut i = input(args(TEXT));
        i.cwd = cwd.into();
        let mut host = Host::new(TEXT);
        failed(
            EvidenceSpans::new(config())
                .unwrap()
                .invoke(i, &mut host)
                .unwrap(),
            "cwd",
        );
        assert_eq!(host.count(), 0);
    }
}

#[test]
fn maximum_identity_lengths_have_bounded_non_echoing_result() {
    let mut cfg = config();
    cfg.sources[0].id = "s".repeat(64);
    cfg.sources[0].path = format!("{}/{}", "p".repeat(255), "q".repeat(256));
    let mut request = args(TEXT);
    request["source_id"] = json!(cfg.sources[0].id);
    request["claims"] = json!(
        (0..32)
            .map(|i| claim(&format!("{i:064}"), 0, 5, "alpha"))
            .collect::<Vec<_>>()
    );
    let mut i = input(request);
    i.cwd = format!("/{}", "w".repeat(4095)).into();
    i.call.id = "v".repeat(128);
    let mut host = Host::new(TEXT);
    host.cwd = i.cwd.to_str().unwrap().into();
    let result = EvidenceSpans::new(cfg)
        .unwrap()
        .invoke(i, &mut host)
        .unwrap();
    assert!(result.ok, "{result:?}");
    assert!(serde_json::to_vec(&result).unwrap().len() <= MAX_RESULT_BYTES);
    assert!(!result.output.contains(TEXT));
}

#[test]
fn unsupported_call_id_does_not_echo_unbounded_result() {
    let mut i = input(args(TEXT));
    i.call.id = "v".repeat(129);
    let mut host = Host::new(TEXT);
    assert!(
        EvidenceSpans::new(config())
            .unwrap()
            .invoke(i, &mut host)
            .is_err()
    );
    assert_eq!(host.count(), 0);
}

#[test]
fn serialized_receipt_budget_rejects_json_escape_expansion() {
    // Host-provided cwd is a lexical path, not opened by the module. Its JSON
    // encoding can be much larger than the UTF-8 string byte count.
    let mut i = input(args(TEXT));
    i.cwd = format!("/{}", "\u{0001}".repeat(4095)).into();
    let mut host = Host::new(TEXT);
    host.cwd = i.cwd.to_str().unwrap().into();
    failed(
        EvidenceSpans::new(config())
            .unwrap()
            .invoke(i, &mut host)
            .unwrap(),
        "result byte bound",
    );
    assert_eq!(host.count(), 1);
}

#[test]
fn metadata_remains_honest_under_trusted_host_transformation() {
    // This demonstrates a trust limit, not an origin-authenticity guarantee.
    let transformed = "alpha transformed";
    let result = run(args(transformed), &mut Host::new(transformed)).unwrap();
    assert!(result.ok);
    assert_eq!(result.metadata[EVIDENCE_KEY]["origin_verified"], false);
    assert_eq!(
        result.metadata[EVIDENCE_KEY]["semantic_entailment"],
        "not_evaluated"
    );
}

#[test]
fn factory_and_definition_keep_existing_tool_boundary() {
    let m = EvidenceSpans::new(config()).unwrap();
    let d = m.definitions();
    assert_eq!(d.len(), 1);
    assert_eq!(d[0].spec.safety, ToolSafety::ReadOnly);
    assert!(!d[0].spec.supports_parallel_tool_calls);
    let good = ProcessComponentExportInitialize::new(
        "tool",
        MODULE_ID,
        "v6",
        ProcessModuleComposition::OrderedMany,
        serde_json::to_value(config()).unwrap(),
        Vec::<String>::new(),
    );
    assert!(proteus_example_evidence_spans::load(good.clone()).is_ok());
    let mut wrong = good;
    wrong.module_id = "other".into();
    assert!(proteus_example_evidence_spans::load(wrong).is_err());
}
