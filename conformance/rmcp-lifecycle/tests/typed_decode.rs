use proteus_mcp_sdk_probes::rich_tool;
use rmcp::model::{
    CallToolResult, InputRequiredResult, ProtocolVersion, ServerCapabilities, ServerResult, Tool,
};
use serde_json::{Value, json};

#[test]
fn valid_supported_tool_fields_survive_exact_typed_roundtrip() {
    let raw = rich_tool();
    let decoded: Tool = serde_json::from_value(raw.clone()).unwrap();
    assert_eq!(serde_json::to_value(decoded).unwrap(), raw);
}

#[test]
fn unknown_tool_and_annotation_fields_are_lost_but_meta_is_not() {
    let control = rich_tool();
    let mut raw = control.clone();
    raw["futureToolField"] = json!({"source":"raw-only"});
    raw["annotations"]["futureHint"] = json!("raw-only");
    raw["_meta"]["futureVendorField"] = json!({"must":"remain"});
    let decoded: Tool = serde_json::from_value(raw.clone()).unwrap();
    let output = serde_json::to_value(decoded).unwrap();
    assert!(raw.get("futureToolField").is_some());
    assert!(output.get("futureToolField").is_none());
    assert!(output["annotations"].get("futureHint").is_none());
    assert_eq!(output["_meta"], raw["_meta"]);
    assert_eq!(output["outputSchema"], control["outputSchema"]);
    assert_eq!(output["annotations"], control["annotations"]);
}

#[test]
fn legacy_experimental_task_required_hint_disappears_at_sdk_decode_not_core_projection() {
    let mut raw = rich_tool();
    raw["execution"] = json!({"taskSupport":"required"});
    let decoded: Tool = serde_json::from_value(raw.clone()).unwrap();
    let output = serde_json::to_value(decoded).unwrap();
    assert_eq!(raw["execution"]["taskSupport"], "required");
    assert!(output.get("execution").is_none());
    assert_eq!(
        output,
        rich_tool(),
        "only the legacy execution extension is lost"
    );
}

#[test]
fn legacy_task_capability_and_modern_extension_are_not_interchangeable() {
    let legacy = json!({"tools":{},"tasks":{"requests":{"tools":{"call":{}}}}});
    let decoded: ServerCapabilities = serde_json::from_value(legacy.clone()).unwrap();
    assert!(!decoded.supports_tasks());
    let output = serde_json::to_value(decoded).unwrap();
    assert!(output.get("tasks").is_none());
    assert_eq!(output["tools"], json!({}));
    let modern = json!({"tools":{},"extensions":{"io.modelcontextprotocol/tasks":{}}});
    let decoded: ServerCapabilities = serde_json::from_value(modern.clone()).unwrap();
    assert!(decoded.supports_tasks());
    assert_eq!(serde_json::to_value(decoded).unwrap(), modern);
}

#[test]
fn missing_required_input_schema_is_not_an_unknown_field_case() {
    let control = rich_tool();
    assert!(serde_json::from_value::<Tool>(control.clone()).is_ok());
    let mut raw = control;
    raw.as_object_mut().unwrap().remove("inputSchema");
    let error = serde_json::from_value::<Tool>(raw).unwrap_err();
    assert!(
        error.to_string().contains("missing field `inputSchema`"),
        "{error}"
    );
}

#[test]
fn malformed_known_schema_field_is_rejected_instead_of_silently_dropped() {
    let mut raw = rich_tool();
    assert!(serde_json::from_value::<Tool>(raw.clone()).is_ok());
    raw["outputSchema"] = json!(["not", "an", "object"]);
    let error = serde_json::from_value::<Tool>(raw).unwrap_err();
    assert!(
        error.to_string().contains("invalid type: sequence"),
        "{error}"
    );
}

#[test]
fn duplicate_known_tool_keys_are_rejected_before_value_roundtrip() {
    let control = r#"{"name":"probe","inputSchema":{"type":"object"}}"#;
    assert!(serde_json::from_str::<Tool>(control).is_ok());
    let duplicate = r#"{"name":"probe","name":"probe","inputSchema":{"type":"object"}}"#;
    let error = serde_json::from_str::<Tool>(duplicate).unwrap_err();
    assert!(
        error.to_string().contains("duplicate field `name`"),
        "{error}"
    );
}

#[test]
fn schema_json_preservation_does_not_mean_semantic_json_schema_validation() {
    let mut raw = rich_tool();
    raw["inputSchema"] = json!({"type":"not-a-json-schema-type"});
    let decoded: Tool = serde_json::from_value(raw.clone()).unwrap();
    assert_eq!(
        serde_json::to_value(decoded).unwrap()["inputSchema"],
        raw["inputSchema"]
    );
    // Core's separate input-schema compiler, not this SDK DTO, owns rejection.
}

#[test]
fn modern_result_discriminator_distinguishes_complete_from_input_required() {
    let complete =
        json!({"resultType":"complete","content":[{"type":"text","text":"done"}],"isError":false});
    let result: ServerResult = serde_json::from_value(complete.clone()).unwrap();
    assert!(matches!(result, ServerResult::CallToolResult(_)));
    let intermediate = json!({"resultType":"input_required","requestState":"opaque-fixture-state"});
    let result: ServerResult = serde_json::from_value(intermediate.clone()).unwrap();
    assert!(matches!(result, ServerResult::InputRequiredResult(_)));
    let error = serde_json::from_value::<CallToolResult>(intermediate).unwrap_err();
    assert!(
        error
            .to_string()
            .contains("requires resultType to be \"complete\""),
        "{error}"
    );
}

#[test]
fn missing_mrtr_payload_is_a_specific_error_not_a_successful_empty_result() {
    let valid = json!({"resultType":"input_required","requestState":"opaque"});
    assert!(serde_json::from_value::<InputRequiredResult>(valid).is_ok());
    let error =
        serde_json::from_value::<InputRequiredResult>(json!({"resultType":"input_required"}))
            .unwrap_err();
    assert!(
        error
            .to_string()
            .contains("requires at least one of inputRequests or requestState"),
        "{error}"
    );
}

#[test]
fn legacy_missing_result_type_and_modern_remote_error_preserve_actual_semantics() {
    let legacy = json!({"content":[{"type":"text","text":"legacy"}],"isError":false});
    let decoded: CallToolResult = serde_json::from_value(legacy.clone()).unwrap();
    assert!(decoded.result_type.is_none());
    assert_eq!(serde_json::to_value(decoded).unwrap(), legacy);
    let remote_error = json!({"resultType":"complete","content":[{"type":"text","text":"remote domain refusal"}],"isError":true,"structuredContent":{"status":"refused"}});
    let decoded: CallToolResult = serde_json::from_value(remote_error.clone()).unwrap();
    assert_eq!(decoded.is_error, Some(true));
    assert_eq!(serde_json::to_value(decoded).unwrap(), remote_error);
}

#[test]
fn modern_version_is_known_but_does_not_itself_choose_a_lifecycle() {
    let version: ProtocolVersion =
        serde_json::from_value(Value::String("2026-07-28".into())).unwrap();
    assert!(ProtocolVersion::KNOWN_VERSIONS.contains(&version));
    assert_eq!(version, ProtocolVersion::V_2026_07_28);
    // Actual Initialize-versus-Discover selection is exercised by stdio tests.
}
