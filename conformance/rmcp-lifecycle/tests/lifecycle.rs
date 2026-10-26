//! Runs only our authored stdio responder with the actual pinned rmcp client.
mod common;
use common::*;
use proteus_mcp_sdk_probes::rich_tool;
use rmcp::{
    ServiceExt,
    model::{CallToolResponse, ProtocolVersion, ServerResult},
    service::{ClientInitializeError, ClientServiceExt},
};
use serde_json::json;
use std::time::Duration;
use tokio::time::timeout;
const FAST: Duration = Duration::from_secs(5);

#[tokio::test]
async fn default_serve_uses_legacy_initialize_and_preserves_typed_tool_metadata() {
    let mut fixture = Fixture::spawn("legacy");
    let connected = timeout(
        FAST,
        info(ProtocolVersion::V_2025_11_25).serve(fixture.pipes()),
    )
    .await
    .unwrap()
    .unwrap();
    let tools = timeout(FAST, connected.list_all_tools())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(tools.len(), 1);
    assert_eq!(serde_json::to_value(&tools[0]).unwrap(), rich_tool());
    let result = timeout(FAST, connected.call_tool_once(call_params()))
        .await
        .unwrap()
        .unwrap();
    let CallToolResponse::Complete(result) = result else {
        panic!("expected completed legacy tool result")
    };
    assert_eq!(result.is_error, Some(false));
    assert!(result.result_type.is_none());
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(
        methods(&trace),
        [
            "initialize",
            "notifications/initialized",
            "tools/list",
            "tools/call"
        ]
    );
    assert_eq!(trace[0]["params"]["protocolVersion"], "2025-11-25");
    assert_distinct_request_ids(&trace);
}

#[tokio::test]
async fn discover_uses_modern_lifecycle_and_per_request_metadata_without_initialize() {
    let mut fixture = Fixture::spawn("modern");
    let connected = connect(
        &mut fixture,
        discover(),
        ProtocolVersion::V_2025_11_25,
        FAST,
    )
    .await
    .unwrap();
    assert_eq!(
        connected.peer_info().unwrap().protocol_version,
        ProtocolVersion::V_2026_07_28
    );
    let tools = timeout(FAST, connected.list_all_tools())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(serde_json::to_value(&tools[0]).unwrap(), rich_tool());
    let result = timeout(FAST, connected.call_tool_once(call_params()))
        .await
        .unwrap()
        .unwrap();
    let CallToolResponse::Complete(result) = result else {
        panic!("expected complete modern result")
    };
    assert_eq!(result.result_type.unwrap().as_str(), "complete");
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(
        methods(&trace),
        ["server/discover", "tools/list", "tools/call"]
    );
    assert_modern_metadata(&trace);
    assert_distinct_request_ids(&trace);
}

#[tokio::test]
async fn setting_modern_version_does_not_switch_initialize_into_discover() {
    let mut fixture = Fixture::spawn("modern");
    let result = timeout(
        FAST,
        info(ProtocolVersion::V_2026_07_28).serve(fixture.pipes()),
    )
    .await
    .expect("default serve must finish within caller budget");
    let trace = fixture.finish().await;
    let Err(ClientInitializeError::JsonRpcError(error)) = result else {
        panic!("expected modern-only initialization refusal from default serve")
    };
    assert_eq!(error.code.0, -32601);
    assert_eq!(error.message, "fixture modern-only: initialize unsupported");
    assert_eq!(methods(&trace), ["initialize"]);
    assert_eq!(trace[0]["params"]["protocolVersion"], "2026-07-28");
}

#[tokio::test]
async fn auto_falls_back_to_explicit_legacy_version_after_legacy_error() {
    let mut fixture = Fixture::spawn("legacy");
    let connected = connect(&mut fixture, auto(), ProtocolVersion::V_2026_07_28, FAST)
        .await
        .unwrap();
    assert_eq!(
        connected.peer_info().unwrap().protocol_version,
        ProtocolVersion::V_2025_11_25
    );
    timeout(FAST, connected.list_all_tools())
        .await
        .unwrap()
        .unwrap();
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(
        methods(&trace),
        [
            "server/discover",
            "initialize",
            "notifications/initialized",
            "tools/list"
        ]
    );
    assert_eq!(trace[1]["params"]["protocolVersion"], "2025-11-25");
    assert_distinct_request_ids(&trace);
}

#[tokio::test]
async fn auto_prefers_modern_discovery_on_a_dual_era_server() {
    let mut fixture = Fixture::spawn("dual");
    let connected = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST)
        .await
        .unwrap();
    assert_eq!(
        connected.peer_info().unwrap().protocol_version,
        ProtocolVersion::V_2026_07_28
    );
    timeout(FAST, connected.list_all_tools())
        .await
        .unwrap()
        .unwrap();
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(methods(&trace), ["server/discover", "tools/list"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn idless_legacy_error_also_allows_fallback_but_is_not_a_correlated_id() {
    let mut fixture = Fixture::spawn("idless-legacy-error");
    let connected = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST)
        .await
        .unwrap();
    timeout(FAST, connected.list_all_tools())
        .await
        .unwrap()
        .unwrap();
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(
        methods(&trace),
        [
            "server/discover",
            "initialize",
            "notifications/initialized",
            "tools/list"
        ]
    );
}

#[tokio::test]
async fn wrong_nonempty_error_id_is_rejected_without_legacy_fallback() {
    let mut fixture = Fixture::spawn("wrong-error-id");
    let result = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST).await;
    let trace = fixture.finish().await;
    let Err(ConnectFailure::Sdk(ClientInitializeError::UncorrelatedErrorResponse {
        expected,
        received,
    })) = result
    else {
        panic!("expected uncorrelated-error variant")
    };
    assert_eq!(serde_json::to_value(expected).unwrap(), trace[0]["id"]);
    assert_eq!(serde_json::to_value(received).unwrap(), "wrong-authored-id");
    assert_eq!(methods(&trace), ["server/discover"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn modern_capability_and_header_rejections_never_fall_back() {
    for (scenario, expected_code, expected_message) in [
        (
            "capability-rejected",
            -32021,
            "authored required capability rejection",
        ),
        ("header-mismatch", -32020, "authored header mismatch"),
    ] {
        let mut fixture = Fixture::spawn(scenario);
        let result = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST).await;
        let trace = fixture.finish().await;
        let Err(ConnectFailure::Sdk(ClientInitializeError::JsonRpcError(error))) = result else {
            panic!("expected modern JSON-RPC rejection for {scenario}")
        };
        assert_eq!(error.code.0, expected_code);
        assert_eq!(error.message, expected_message);
        assert_eq!(methods(&trace), ["server/discover"]);
        assert_modern_metadata(&trace);
    }
}

#[tokio::test]
async fn unsupported_modern_version_is_not_reinterpreted_as_legacy() {
    let mut fixture = Fixture::spawn("unsupported-version");
    let result = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST).await;
    let trace = fixture.finish().await;
    let Err(ConnectFailure::Sdk(ClientInitializeError::NoCompatibleProtocolVersion {
        client_supported,
        server_supported,
    })) = result
    else {
        panic!("expected version-negotiation failure")
    };
    assert_eq!(client_supported, vec![ProtocolVersion::V_2026_07_28]);
    assert_eq!(
        serde_json::to_value(server_supported).unwrap(),
        json!(["2099-01-01"])
    );
    assert_eq!(methods(&trace), ["server/discover"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn discover_only_mode_does_not_fall_back_even_on_known_legacy_error() {
    let mut fixture = Fixture::spawn("legacy");
    let result = connect(
        &mut fixture,
        discover(),
        ProtocolVersion::V_2025_11_25,
        FAST,
    )
    .await;
    let trace = fixture.finish().await;
    let Err(ConnectFailure::Sdk(ClientInitializeError::JsonRpcError(error))) = result else {
        panic!("expected explicit discover-only failure")
    };
    assert_eq!(error.code.0, -32601);
    assert_eq!(methods(&trace), ["server/discover"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn failed_legacy_fallback_preserves_both_phase_errors() {
    let mut fixture = Fixture::spawn("fallback-fails");
    let result = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST).await;
    let trace = fixture.finish().await;
    let Err(ConnectFailure::Sdk(ClientInitializeError::LegacyFallbackFailed {
        discover,
        fallback,
    })) = result
    else {
        panic!("expected two-phase failure")
    };
    let ClientInitializeError::JsonRpcError(discover) = *discover else {
        panic!("discover reason lost")
    };
    let ClientInitializeError::JsonRpcError(fallback) = *fallback else {
        panic!("fallback reason lost")
    };
    assert_eq!(discover.code.0, -32601);
    assert_eq!(fallback.code.0, -32000);
    assert_eq!(methods(&trace), ["server/discover", "initialize"]);
}

#[tokio::test]
async fn wrong_success_id_is_rejected_without_publishing_a_client() {
    let mut fixture = Fixture::spawn("wrong-success-id");
    let result = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST).await;
    let trace = fixture.finish().await;
    let Err(ConnectFailure::Sdk(ClientInitializeError::ConflictInitResponseId(expected, received))) =
        result
    else {
        panic!("expected success correlation error")
    };
    assert_eq!(serde_json::to_value(expected).unwrap(), trace[0]["id"]);
    assert_eq!(serde_json::to_value(received).unwrap(), "wrong-authored-id");
    assert_eq!(methods(&trace), ["server/discover"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn legacy_result_shape_during_discover_is_not_accepted_as_success() {
    let mut fixture = Fixture::spawn("wrong-discover-result");
    let result = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST).await;
    let trace = fixture.finish().await;
    let Err(ConnectFailure::Sdk(ClientInitializeError::ExpectedInitResult(Some(
        ServerResult::InitializeResult(_),
    )))) = result
    else {
        panic!("expected wrong-result-type failure")
    };
    assert_eq!(methods(&trace), ["server/discover"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn transport_close_is_not_a_legacy_negotiation_signal() {
    let mut fixture = Fixture::spawn("close-during-discover");
    let result = connect(&mut fixture, auto(), ProtocolVersion::V_2025_11_25, FAST).await;
    let trace = fixture.finish().await;
    let Err(ConnectFailure::Sdk(ClientInitializeError::ConnectionClosed(context))) = result else {
        panic!("expected transport closure")
    };
    assert_eq!(context, "discover response");
    assert_eq!(methods(&trace), ["server/discover"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn caller_deadline_can_expire_before_public_sdk_auto_probe_timeout() {
    let mut fixture = Fixture::spawn("silent-discover");
    let result = connect(
        &mut fixture,
        auto(),
        ProtocolVersion::V_2025_11_25,
        Duration::from_secs(2),
    )
    .await;
    let trace = fixture.finish().await;
    assert!(
        matches!(result, Err(ConnectFailure::Deadline)),
        "expected caller deadline, not SDK/server error"
    );
    assert_eq!(
        methods(&trace),
        ["server/discover"],
        "probe must actually reach the child; initialize must not run"
    );
}

#[tokio::test]
async fn unanswered_discovery_falls_back_within_caller_budget() {
    let mut fixture = Fixture::spawn("silent-discover");
    // Public API source fixes its probe timeout at 10s; the observable assertion
    // here is fallback after an unanswered probe within the 20s caller budget.
    // No elapsed-time/default-duration measurement or benchmark is claimed.
    let connected = connect(
        &mut fixture,
        auto(),
        ProtocolVersion::V_2026_07_28,
        Duration::from_secs(20),
    )
    .await
    .unwrap();
    timeout(FAST, connected.list_all_tools())
        .await
        .unwrap()
        .unwrap();
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(
        methods(&trace),
        [
            "server/discover",
            "initialize",
            "notifications/initialized",
            "tools/list"
        ]
    );
    assert_eq!(trace[1]["params"]["protocolVersion"], "2025-11-25");
}

#[tokio::test]
async fn caller_abort_during_observed_probe_does_not_start_legacy_fallback() {
    let mut fixture = Fixture::spawn("silent-discover");
    let pipes = fixture.pipes();
    let task = tokio::spawn(async move {
        info(ProtocolVersion::V_2025_11_25)
            .serve_with_lifecycle(pipes, auto())
            .await
    });
    fixture.observed_method("server/discover").await;
    task.abort();
    let joined = task.await;
    let trace = fixture.finish().await;
    assert!(joined.unwrap_err().is_cancelled());
    assert_eq!(methods(&trace), ["server/discover"]);
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn oneshot_mrtr_response_is_explicit_and_does_not_run_followup_rounds() {
    let mut fixture = Fixture::spawn("modern-input-required");
    let connected = connect(
        &mut fixture,
        discover(),
        ProtocolVersion::V_2025_11_25,
        FAST,
    )
    .await
    .unwrap();
    let response = timeout(FAST, connected.call_tool_once(call_params()))
        .await
        .unwrap()
        .unwrap();
    let CallToolResponse::InputRequired(result) = response else {
        panic!("expected explicit MRTR intermediate result")
    };
    assert_eq!(
        result.request_state.as_deref(),
        Some("opaque-authored-state")
    );
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(
        methods(&trace),
        ["server/discover", "tools/call"],
        "no automatic model/tool/task continuation"
    );
    assert_modern_metadata(&trace);
}

#[tokio::test]
async fn remote_domain_error_is_not_transport_success_or_failure_by_assumption() {
    let mut fixture = Fixture::spawn("modern-domain-error");
    let connected = connect(
        &mut fixture,
        discover(),
        ProtocolVersion::V_2025_11_25,
        FAST,
    )
    .await
    .unwrap();
    let response = timeout(FAST, connected.call_tool_once(call_params()))
        .await
        .unwrap()
        .unwrap();
    let CallToolResponse::Complete(result) = response else {
        panic!("expected completed protocol result")
    };
    assert_eq!(result.is_error, Some(true));
    assert_eq!(result.structured_content.unwrap()["status"], "refused");
    shutdown(connected).await;
    let trace = fixture.finish().await;
    assert_eq!(methods(&trace), ["server/discover", "tools/call"]);
}
