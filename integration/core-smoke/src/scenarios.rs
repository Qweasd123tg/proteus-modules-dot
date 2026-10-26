use crate::support::*;
use anyhow::{Result, ensure};
use proteus_core::core::{
    AppConfig, AssemblyPlan, HeadlessApprovalTransport, ModelExecutionBinding, ModuleCatalog,
    RuntimeRegistry,
};
use proteus_module_sdk::contracts::{
    contracts::{ContextBuildInput, ExecutionAttribution, HookEvent},
    domain::{AgentTask, PermissionMode, ToolCall, ToolSafety},
};
use serde_json::{Value, json};
use std::path::Path;

pub async fn run() -> Result<Vec<Value>> {
    let bins = required_path("PROTEUS_EXAMPLE_BIN_DIR")?;
    let sources = required_path("PROTEUS_EXAMPLES_SOURCE_DIR")?;
    let cwd = required_path("PROTEUS_SMOKE_WORKSPACE")?;
    ensure!(
        cwd.is_dir() && std::fs::read_dir(&cwd)?.next().is_none(),
        "workspace must be empty"
    );
    let fixture = std::env::current_exe()?;
    let mut report = vec![];
    for file in [
        "pi-ready-steps/proteus.offline.example.toml",
        "letta-evidence-blocks/host.example.toml",
        "hermes-verify-evidence/profile.fragment.toml",
    ] {
        let path = sources.join(file);
        let config = AppConfig::load(Some(&path)).await?;
        let catalog = ModuleCatalog::from_config(&config)?;
        let plan = AssemblyPlan::resolve(config, Some(&path), cwd.clone(), &catalog)?;
        plan.ensure_valid()?;
        check(
            &mut report,
            "original_profile_load_and_static_assembly",
            json!({"file":file,"runtime_launched":false,"components":plan.components.len(),"hooks":plan.hooks}),
        );
    }
    let baseline = serde_json::to_value(base())?;
    let _: AppConfig = serde_json::from_value(baseline.clone())?;
    let mut unknown = baseline;
    unknown["unknown_probe"] = json!(true);
    let error =
        serde_json::from_value::<AppConfig>(unknown).expect_err("unknown config field accepted");
    ensure!(
        error.to_string().contains("unknown field `unknown_probe`"),
        "unexpected strict-config diagnostic: {error}"
    );
    check(&mut report, "strict_config_unknown_field", json!({}));

    let mut pi = base();
    pi.tools.enabled = vec!["planning.ready_steps".into()];
    pi.components.insert(
        "ready_steps".into(),
        component(
            &bins.join("proteus-pi-ready-steps"),
            json!({"tool":{"planning.ready_steps":{"timeout_ms":5000}}}),
            false,
        ),
    );
    config_value(&mut pi, "tool", "planning.ready_steps", json!({}));
    let denied = RuntimeRegistry::from_config(&pi, cwd.clone())?;
    let denied_result = tools(&denied, scope())
        .execute(cwd.clone(), plan_call("deny"))
        .await?;
    ensure!(
        !denied_result.ok
            && denied_result.call_id == "deny"
            && denied_result.error.as_deref()
                == Some("policy deny_all rejects tool 'planning.ready_steps'"),
        "unexpected deny result: {denied_result:?}"
    );
    check(
        &mut report,
        "pi_bound_tools_default_deny",
        json!({"result":denied_result}),
    );
    drop(denied);

    let mut disabled = pi.clone();
    disabled.tools.enabled.clear();
    let disabled_registry = RuntimeRegistry::from_config(&disabled, cwd.clone())?;
    ensure!(
        disabled_registry
            .tools
            .get("planning.ready_steps")
            .is_none(),
        "component discovery enabled a tool"
    );
    check(&mut report, "pi_discovery_does_not_enable", json!({}));
    drop(disabled_registry);

    pi.modules.policy = Some("smoke.read_only".into());
    pi.components.insert(
        "fixture".into(),
        component(&fixture, json!({"policy":{"smoke.read_only":{}}}), true),
    );
    config_value(&mut pi, "policy", "smoke.read_only", json!({}));
    let registry = RuntimeRegistry::from_config(&pi, cwd.clone())?;
    ensure!(
        registry.tools.spec("planning.ready_steps")?.safety == ToolSafety::ReadOnly,
        "safety changed"
    );
    let bound = tools(&registry, scope());
    let specs = bound.visible_specs(&cwd);
    ensure!(
        specs.len() == 1 && specs[0].name == "planning.ready_steps",
        "visibility policy mismatch"
    );
    let result = bound.execute(cwd.clone(), plan_call("real-host")).await?;
    ensure!(result.ok, "planning call failed: {result:?}");
    let output: Value = serde_json::from_str(&result.output)?;
    ensure!(
        output["ready"] == json!(["review"]) && output["advisory_only"] == true,
        "wrong readiness response"
    );
    check(
        &mut report,
        "pi_real_core_bound_policy_and_invocation",
        json!({"output":output}),
    );

    let invalid = bound
        .execute(
            cwd.clone(),
            ToolCall::new(
                "invalid",
                "planning.ready_steps",
                json!({"nodes":[],"failure_policy":"ignored"}),
            ),
        )
        .await?;
    ensure!(
        !invalid.ok && invalid.metadata["validation_error"] == true,
        "Core schema boundary did not reject malformed arguments"
    );
    check(
        &mut report,
        "pi_core_schema_rejection",
        json!({"result":invalid}),
    );

    let cancelled_scope = scope();
    cancelled_scope.cancellation.cancel();
    let error = tools(&registry, cancelled_scope)
        .execute(cwd.clone(), plan_call("cancelled"))
        .await
        .expect_err("pre-canceled call accepted");
    ensure!(
        error.to_string().contains("canceled"),
        "wrong cancellation error: {error:#}"
    );
    ensure!(
        bound
            .execute(cwd.clone(), plan_call("after-cancel"))
            .await?
            .ok,
        "fresh execution poisoned by cancellation"
    );
    check(
        &mut report,
        "pi_pre_cancel_and_next_execution",
        json!({"error":error.to_string(),"not_tested":"in-flight cancellation"}),
    );
    drop(bound);
    drop(registry);

    let mut duplicate = pi.clone();
    duplicate.components.insert(
        "duplicate".into(),
        duplicate.components["ready_steps"].clone(),
    );
    let error = ModuleCatalog::from_config(&duplicate)
        .err()
        .expect("duplicate export accepted");
    ensure!(
        error
            .to_string()
            .contains("duplicate process component export"),
        "wrong duplicate error"
    );
    check(
        &mut report,
        "duplicate_export_identity_rejected",
        json!({"error":error.to_string()}),
    );

    let mut hermes = base();
    hermes.modules.hooks = vec!["hermes.verify_evidence".into()];
    hermes.components.insert(
        "hermes".into(),
        component(
            &bins.join("proteus-example-hermes-verify-evidence"),
            json!({"hook":{"hermes.verify_evidence":{"timeout_ms":5000}}}),
            false,
        ),
    );
    config_value(
        &mut hermes,
        "hook",
        "hermes.verify_evidence",
        json!({"mutating_tools":["fixture_write"],"verification_tools":["fixture_verify"],"max_nudges":2,"max_history_parts":100,"on_exhaustion":"error"}),
    );
    let registry = RuntimeRegistry::from_config(&hermes, cwd.clone())?;
    let execution_scope = scope();
    let execution = registry.execution_context(
        ModelExecutionBinding::detached(execution_scope.clone()),
        std::sync::Arc::new(HeadlessApprovalTransport),
        PermissionMode::Normal,
    )?;
    ensure!(execution.model.is_none(), "unexpected model");
    let mutation = vec![
        call_message("write", "fixture_write"),
        result_message("write", json!({})),
    ];
    let event = execution
        .hooks
        .apply(before_stop(&cwd, &execution_scope, mutation.clone(), 0))
        .await?;
    ensure!(
        matches!(
            event,
            HookEvent::BeforeStop {
                continuation: Some(_),
                ..
            }
        ),
        "missing evidence did not request continuation"
    );
    check(
        &mut report,
        "hermes_real_core_chain_missing_evidence",
        json!({"history_is_synthetic":true,"event":event}),
    );
    let error = execution
        .hooks
        .apply(before_stop(&cwd, &execution_scope, mutation.clone(), 2))
        .await
        .expect_err("exhaustion accepted");
    let diagnostic = format!("{error:#}");
    ensure!(
        diagnostic.contains("verification evidence remains missing after 2 continuation attempts")
            && diagnostic.contains("completion is not accepted"),
        "unexpected exhaustion error: {diagnostic}"
    );
    check(
        &mut report,
        "hermes_real_core_chain_fail_closed_exhaustion",
        json!({"error":error.to_string()}),
    );
    let verification = vec![
        call_message("verify", "fixture_verify"),
        result_message(
            "verify",
            json!({"proteus.example.verification":{"schema_version":1,"status":"passed","cwd":cwd,"checks_executed":["synthetic-only:no-check-executed"]}}),
        ),
    ];
    let mut accepted = mutation.clone();
    accepted.extend(verification.clone());
    let event = execution
        .hooks
        .apply(before_stop(&cwd, &execution_scope, accepted, 0))
        .await?;
    ensure!(
        matches!(
            event,
            HookEvent::BeforeStop {
                continuation: None,
                ..
            }
        ),
        "matching synthetic receipt rejected"
    );
    check(
        &mut report,
        "hermes_real_core_chain_synthetic_receipt",
        json!({"no_real_verifier":true,"event":event}),
    );
    let mut stale = verification;
    stale.extend(mutation);
    let event = execution
        .hooks
        .apply(before_stop(&cwd, &execution_scope, stale, 0))
        .await?;
    ensure!(
        matches!(
            event,
            HookEvent::BeforeStop {
                continuation: Some(_),
                ..
            }
        ),
        "stale receipt accepted"
    );
    check(
        &mut report,
        "hermes_real_core_chain_stale_receipt",
        json!({}),
    );
    let error = execution
        .hooks
        .apply(before_stop(&cwd, &scope(), vec![], 0))
        .await
        .expect_err("cross-execution attribution accepted");
    ensure!(
        error.to_string().contains("attribution"),
        "wrong attribution error"
    );
    check(
        &mut report,
        "hermes_host_attribution_binding",
        json!({"error":error.to_string()}),
    );
    drop(execution);
    drop(registry);

    let mut letta = base();
    letta.modules.context = Some("smoke.provider_relay".into());
    letta.components.insert(
        "relay".into(),
        component(
            &fixture,
            json!({"context":{"smoke.provider_relay":{}}}),
            true,
        ),
    );
    config_value(&mut letta, "context", "smoke.provider_relay", json!({}));
    letta.components.insert(
        "letta".into(),
        component(
            &bins.join("proteus-example-letta-evidence-blocks"),
            json!({"context_provider":{"letta.evidence_blocks":{"timeout_ms":5000}}}),
            false,
        ),
    );
    let original = AppConfig::load(Some(
        &sources.join("letta-evidence-blocks/host.example.toml"),
    ))
    .await?;
    config_value(
        &mut letta,
        "context_provider",
        "letta.evidence_blocks",
        original.module_config["context_provider"]["letta.evidence_blocks"].clone(),
    );
    let registry = RuntimeRegistry::from_config(&letta, cwd.clone())?;
    let context = registry
        .context
        .build(context_input(&cwd, "storage SQLite database"))
        .await?;
    ensure!(
        context.chunks.len() == 1
            && context.chunks[0].content.contains("storage-decision")
            && !context.chunks[0].content.contains("obsolete-note"),
        "selection/tombstone mismatch: {context:?}"
    );
    ensure!(
        context.chunks[0]
            .content
            .starts_with("UNTRUSTED REFERENCE DATA."),
        "trust annotation lost"
    );
    check(
        &mut report,
        "letta_real_core_callback_selection",
        json!({"bundle":context,"relay_is_authored_fixture":true}),
    );
    let context = registry.context.build(context_input(&cwd, "")).await?;
    ensure!(context.chunks.is_empty(), "empty query exposed evidence");
    check(&mut report, "letta_real_core_empty_query", json!({}));
    let error = registry
        .context
        .build(context_input(&cwd, &"x".repeat(4097)))
        .await
        .expect_err("overlong query accepted");
    ensure!(
        format!("{error:#}").contains("4096"),
        "unexpected overlong-query error: {error:#}"
    );
    ensure!(
        !registry
            .context
            .build(context_input(&cwd, "SQLite"))
            .await?
            .chunks
            .is_empty(),
        "next invocation poisoned by provider error"
    );
    check(
        &mut report,
        "letta_callback_error_and_next_invocation",
        json!({"error":format!("{error:#}")}),
    );
    drop(registry);

    let mut missing = letta.clone();
    missing.components.remove("letta");
    missing.module_config.remove("context_provider");
    let registry = RuntimeRegistry::from_config(&missing, cwd.clone())?;
    let error = registry
        .context
        .build(context_input(&cwd, "storage"))
        .await
        .expect_err("missing provider accepted");
    ensure!(
        format!("{error:#}").contains("unknown context provider"),
        "wrong missing provider error: {error:#}"
    );
    check(
        &mut report,
        "letta_missing_provider_no_fallback",
        json!({"error":format!("{error:#}")}),
    );
    drop(registry);

    let mut invalid = letta;
    invalid
        .module_config
        .get_mut("context_provider")
        .unwrap()
        .get_mut("letta.evidence_blocks")
        .unwrap()["max_results"] = json!(0);
    let error = RuntimeRegistry::from_config(&invalid, cwd.clone())
        .err()
        .expect("invalid provider config accepted");
    ensure!(
        format!("{error:#}").contains("failed strict initialization"),
        "unexpected config error: {error:#}"
    );
    check(
        &mut report,
        "letta_changed_config_initialization_fails",
        json!({"error":format!("{error:#}"), "only_config_change":"max_results=0", "diagnostic_limit":"Core hides the inner module error; this host check does not prove the failure reason. Same executable and otherwise identical valid config initialized above."}),
    );
    ensure!(
        std::fs::read_dir(&cwd)?.next().is_none(),
        "module smoke wrote workspace files"
    );
    check(
        &mut report,
        "workspace_remains_empty",
        json!({"scope":"workspace only; not OS-wide sandbox evidence"}),
    );
    Ok(report)
}
fn context_input(cwd: &Path, query: &str) -> ContextBuildInput {
    let execution_scope = scope();
    let attribution = ExecutionAttribution::detached(execution_scope.execution_id);
    ContextBuildInput::new(
        AgentTask::new(query, cwd.to_path_buf()),
        execution_scope,
        attribution,
    )
}
