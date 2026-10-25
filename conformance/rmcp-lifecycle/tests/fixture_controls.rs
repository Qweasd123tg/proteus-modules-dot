use proteus_mcp_sdk_probes::fixture::{Responder, Scenario, Step};
use serde_json::json;

#[test]
fn modern_fixture_actually_rejects_missing_metadata_instead_of_accepting_every_probe() {
    let mut server = Responder::new(Scenario::Modern);
    let missing = json!({"jsonrpc":"2.0","id":1,"method":"server/discover","params":{}});
    let Step::Reply(error) = server.handle(&missing) else {
        panic!("expected reply")
    };
    assert_eq!(error["error"]["code"], -32021);
    let mut valid = missing;
    valid["params"]["_meta"] = json!({"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientInfo":{"name":"authored-sdk-probe","version":"0.1.0"},"io.modelcontextprotocol/clientCapabilities":{}});
    let Step::Reply(success) = server.handle(&valid) else {
        panic!("expected reply")
    };
    assert_eq!(
        success["result"]["supportedVersions"],
        json!(["2026-07-28"])
    );
    assert!(success.get("error").is_none());
}

#[test]
fn fixture_requires_handshake_and_preserves_request_identity() {
    let mut server = Responder::new(Scenario::Legacy);
    let request = json!({"jsonrpc":"2.0","id":"exact-call","method":"tools/list","params":{}});
    let Step::Reply(error) = server.handle(&request) else {
        panic!("expected reply")
    };
    assert_eq!(error["id"], "exact-call");
    assert_eq!(error["error"]["code"], -32000);
    assert_eq!(error["error"]["message"], "fixture handshake missing");
    let initialize = json!({"jsonrpc":"2.0","id":2,"method":"initialize","params":{"clientInfo":{"name":"authored-sdk-probe"}}});
    let Step::Reply(success) = server.handle(&initialize) else {
        panic!("expected reply")
    };
    assert_eq!(success["result"]["protocolVersion"], "2025-11-25");
    let mut call = json!({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"public_alias_not_raw_name","arguments":{"id":"fixture-42"}}});
    let Step::Reply(error) = server.handle(&call) else {
        panic!("expected reply")
    };
    assert_eq!(error["error"]["message"], "fixture unknown raw tool name");
    call["params"]["name"] = json!("lookup.record");
    call["params"]["arguments"] = json!({});
    let Step::Reply(error) = server.handle(&call) else {
        panic!("expected reply")
    };
    assert_eq!(
        error["error"]["message"],
        "fixture requires exact authored arguments"
    );
    call["params"]["arguments"] = json!({"id":"fixture-42"});
    let Step::Reply(success) = server.handle(&call) else {
        panic!("expected reply")
    };
    assert_eq!(success["id"], 3);
    assert_eq!(success["result"]["isError"], false);
}
