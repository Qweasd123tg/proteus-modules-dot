//! Actual pinned Core, frozen portable module, authored model-free fixtures only.
mod fixture;
mod support;

use anyhow::{Result, ensure};
use proteus_core::core::{ModuleCatalog, RuntimeRegistry};
use proteus_module_sdk::contracts::domain::{ToolCall, ToolSafety, validate_tool_call_args};
use serde_json::{Value, json};
use std::{fs, path::Path};
use support::*;

const ORIGINAL: &str = "---\nname: review\ndescription: Authored Core pair probe\nallowed-tools: Bash(*)\nmetadata:\n  owner: authored-fixture\n---\nOriginal authored body.\n";
const CHANGED: &str = "---\nname: review\ndescription: Authored Core pair probe\nallowed-tools: Bash(*)\nmetadata:\n  owner: authored-fixture\n---\nChanged authored body only.\n";

fn main() -> Result<()> {
    if std::env::args().nth(1).as_deref() == Some("--fixture") {
        return proteus_module_sdk::run(fixture::load);
    }
    ensure!(
        std::env::args().len() == 1,
        "no positional arguments supported"
    );
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()?;
    let report = runtime.block_on(run())?;
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({"schema_version":1,
        "core_commit":"3f36a003b4f3fde2242fc80f7aedac00dd127d1d",
        "scope":"real Core RuntimeRegistry/context callback/BoundTools, frozen portable module, authored model-free component probe",
        "not_claimed":["complete agent turn","reference-pack context/policy","OS sandbox","in-flight cancellation settlement","foreign scripts or services"],
        "checks":report}))?
    );
    Ok(())
}
fn write_skill(root: &Path, name: &str, text: &str) -> Result<()> {
    fs::create_dir_all(root.join(name))?;
    fs::write(root.join(name).join("SKILL.md"), text)?;
    Ok(())
}
async fn run() -> Result<Vec<Value>> {
    let binary = required_path("PROTEUS_PORTABLE_SKILLS_BINARY")?;
    ensure!(binary.is_file(), "module binary must be a file");
    let cwd = required_path("PROTEUS_SKILLS_PROBE_WORKSPACE")?;
    ensure!(
        cwd.is_dir() && fs::read_dir(&cwd)?.next().is_none(),
        "workspace must be a fresh empty directory"
    );
    let a = cwd.join("root-a");
    let b = cwd.join("root-b");
    write_skill(&a, "review", ORIGINAL)?;
    write_skill(&b, "review", ORIGINAL)?;
    let config = config(&binary, &a, &a)?;
    let catalog = ModuleCatalog::from_config(&config)?;
    // This is a config assertion, not a PID-count or isolation claim.
    let provider_config = serde_json::to_value(&config.components["portable-provider"])?;
    let tool_config = serde_json::to_value(&config.components["portable-tool"])?;
    ensure!(
        provider_config["exports"].as_object().unwrap().len() == 1
            && tool_config["exports"].as_object().unwrap().len() == 1,
        "portable components must each bind one slot"
    );
    drop(catalog);
    let mut report = vec![];
    check(
        &mut report,
        "configured_single_export_pair",
        json!({"provider_slot":"context_provider/v4","tool_slot":"tool/v6","default_launch":"trusted; not a sandbox claim"}),
    );
    let registry = RuntimeRegistry::from_config(&config, cwd.clone())?;
    for name in ["portable_skill_catalog", "portable_skill_load"] {
        ensure!(
            registry.tools.spec(name)?.safety == ToolSafety::ReadOnly,
            "unexpected tool safety"
        );
    }
    let tools = bound(&registry);
    let first = provider_entry(&registry, &cwd).await?;
    let result = tools
        .execute(cwd.clone(), load_call("provider-to-load", &first))
        .await?;
    ensure!(
        result.metadata["hints_grant_authority"] == false,
        "module hint warning metadata lost"
    );
    let loaded = success(result, "provider-to-load")?;
    ensure!(loaded["body"] == "Original authored body.", "body mismatch");
    ensure!(
        loaded["skill"]["fields"]["allowed-tools"] == "Bash(*)",
        "hint data not retained"
    );
    ensure!(
        loaded["warning"]
            .as_str()
            .is_some_and(|s| s.starts_with("SKILL CONTENT IS UNTRUSTED DATA.")),
        "loaded content warning missing"
    );
    ensure!(
        loaded["skill"]["path"] == first["path"] && loaded["skill"]["sha256"] == first["sha256"],
        "loaded source identity mismatch"
    );
    check(
        &mut report,
        "context_to_bound_load",
        json!({"id":first["id"],"sha256":first["sha256"],"call_id":"provider-to-load","json_complete":true,"hint_is_data":true}),
    );
    let missing_path = ToolCall::new(
        "missing-path",
        "portable_skill_load",
        json!({"id":first["id"],"sha256":first["sha256"]}),
    );
    let load_spec = registry.tools.spec("portable_skill_load")?;
    let expected_validation = validate_tool_call_args(&missing_path, &load_spec)
        .ok_or_else(|| anyhow::anyhow!("missing catalog_path unexpectedly validated"))?;
    ensure!(
        expected_validation.contains("schema '/required'"),
        "negative control did not reach required-field validation: {expected_validation}"
    );
    let invalid = tools.execute(cwd.clone(), missing_path).await?;
    expected_error(&invalid, "missing-path", &expected_validation)?;
    ensure!(
        invalid.metadata["validation_error"] == true
            && invalid.error.as_deref() == Some(expected_validation.as_str()),
        "Core did not preserve exact missing catalog_path validation diagnostic"
    );
    check(
        &mut report,
        "schema_required_catalog_path",
        json!({"core_validation_error":true,"error":expected_validation}),
    );

    write_skill(&a, "review", CHANGED)?;
    let stale = tools
        .execute(cwd.clone(), load_call("stale-body", &first))
        .await?;
    expected_error(&stale, "stale-body", "skill changed since catalog")?;
    check(
        &mut report,
        "body_change_rejected",
        json!({"same_id":true,"same_frontmatter":true,"error":stale.error}),
    );
    let refreshed = success(
        tools
            .execute(
                cwd.clone(),
                ToolCall::new("refresh", "portable_skill_catalog", json!({})),
            )
            .await?,
        "refresh",
    )?;
    let fresh = refreshed["catalog"]["skills"][0].clone();
    ensure!(
        fresh["id"] == first["id"]
            && fresh["path"] == first["path"]
            && fresh["sha256"] != first["sha256"],
        "refresh did not replace just body identity"
    );
    let loaded = success(
        tools
            .execute(cwd.clone(), load_call("fresh-load", &fresh))
            .await?,
        "fresh-load",
    )?;
    ensure!(
        loaded["body"] == "Changed authored body only.",
        "refreshed body mismatch"
    );
    check(
        &mut report,
        "catalog_refresh_same_registry",
        json!({"same_registry":true,"refreshed_sha256":fresh["sha256"]}),
    );
    drop(tools);
    drop(registry);

    let mut denied_config = config.clone();
    denied_config.modules.policy = None;
    let denied = RuntimeRegistry::from_config(&denied_config, cwd.clone())?;
    let result = bound(&denied)
        .execute(cwd.clone(), load_call("default-deny", &fresh))
        .await?;
    expected_error(
        &result,
        "default-deny",
        "policy deny_all rejects tool 'portable_skill_load'",
    )?;
    check(
        &mut report,
        "default_deny_not_overridden_by_hints",
        json!({"error":result.error,"configured_allowed_tools_is_data":true}),
    );
    drop(denied);

    // Exact byte equality is essential: digest mismatch must not hide source mismatch.
    write_skill(&b, "review", CHANGED)?;
    ensure!(
        fs::read(a.join("review/SKILL.md"))? == fs::read(b.join("review/SKILL.md"))?,
        "mismatch control bytes differ"
    );
    let mismatched_config = support::config(&binary, &a, &b)?;
    let mismatched = RuntimeRegistry::from_config(&mismatched_config, cwd.clone())?;
    let from_a = provider_entry(&mismatched, &cwd).await?;
    let result = bound(&mismatched)
        .execute(cwd.clone(), load_call("wrong-source", &from_a))
        .await?;
    expected_error(
        &result,
        "wrong-source",
        "skill source differs from catalog_path",
    )?;
    let matching_b_catalog = success(
        bound(&mismatched)
            .execute(
                cwd.clone(),
                ToolCall::new("source-b-catalog", "portable_skill_catalog", json!({})),
            )
            .await?,
        "source-b-catalog",
    )?;
    let from_b = &matching_b_catalog["catalog"]["skills"][0];
    ensure!(
        from_b["sha256"] == from_a["sha256"] && from_b["path"] != from_a["path"],
        "source mismatch control must preserve digest and change path"
    );
    let matching_b = success(
        bound(&mismatched)
            .execute(cwd.clone(), load_call("matching-source-b", from_b))
            .await?,
        "matching-source-b",
    )?;
    ensure!(
        matching_b["body"] == "Changed authored body only.",
        "same registry did not load its matching source"
    );
    check(
        &mut report,
        "same_bytes_different_source_rejected",
        json!({"both_files_exist":true,"identical_bytes":true,"error":result.error,"matching_source_same_registry_passed":true}),
    );
    drop(mismatched);

    let mut disabled_config = config.clone();
    disabled_config.addons.disabled_skills = vec!["probe:review".into()];
    let disabled = RuntimeRegistry::from_config(&disabled_config, cwd.clone())?;
    let context = disabled.context.build(context_input(&cwd)).await?;
    ensure!(
        context.chunks.is_empty(),
        "globally disabled skill leaked into provider context"
    );
    let disabled_tools = bound(&disabled);
    let snapshot = success(
        disabled_tools
            .execute(
                cwd.clone(),
                ToolCall::new("disabled-catalog", "portable_skill_catalog", json!({})),
            )
            .await?,
        "disabled-catalog",
    )?;
    ensure!(
        snapshot["catalog"]["skills"] == json!([]) && snapshot["catalog"]["skipped_disabled"] == 1,
        "global disabled IDs not propagated to tool catalog"
    );
    let result = disabled_tools
        .execute(cwd.clone(), load_call("disabled-load", &fresh))
        .await?;
    expected_error(&result, "disabled-load", "skill is disabled")?;
    ensure!(
        fs::read_to_string(a.join("review/SKILL.md"))? == CHANGED,
        "disabled control is not the previously loadable file"
    );
    check(
        &mut report,
        "global_disabled_provider_and_loader",
        json!({"existing_valid_file":true,"context_empty":true,"error":result.error}),
    );
    drop(disabled_tools);
    drop(disabled);

    let mut provider_only = config.clone();
    provider_only
        .module_config
        .get_mut("context_provider")
        .unwrap()
        .get_mut("portable.skills")
        .unwrap()["disabled"] = json!(["probe:review"]);
    let independent = RuntimeRegistry::from_config(&provider_only, cwd.clone())?;
    ensure!(
        independent
            .context
            .build(context_input(&cwd))
            .await?
            .chunks
            .is_empty(),
        "provider-only disabled setting not applied"
    );
    let output = success(
        bound(&independent)
            .execute(cwd.clone(), load_call("independent-load", &fresh))
            .await?,
        "independent-load",
    )?;
    ensure!(
        output["body"] == "Changed authored body only.",
        "independent tool configuration unexpectedly revoked"
    );
    check(
        &mut report,
        "provider_only_disabled_does_not_revoke_tool",
        json!({"documented_non_guarantee":"per-export configs are independent; use global disabled ID or align both configs"}),
    );
    drop(independent);

    let large_root = cwd.join("large-body");
    let large_body = "x".repeat(100_000);
    write_skill(
        &large_root,
        "review",
        &format!("---\nname: review\ndescription: Large authored valid body\n---\n{large_body}\n"),
    )?;
    let large = RuntimeRegistry::from_config(
        &support::config(&binary, &large_root, &large_root)?,
        cwd.clone(),
    )?;
    let entry = provider_entry(&large, &cwd).await?;
    let result = bound(&large)
        .execute(cwd.clone(), load_call("large-valid-load", &entry))
        .await?;
    let output_bytes = result.output.len();
    ensure!(
        output_bytes > 100_000 && output_bytes <= 131_072,
        "expected valid module text below its cap"
    );
    let output = success(result, "large-valid-load")?;
    ensure!(
        output["body"] == large_body,
        "large JSON body was not preserved"
    );
    check(
        &mut report,
        "large_valid_body_below_default_host_cap",
        json!({"body_bytes":100_000,"output_bytes":output_bytes,"host_default_bytes":200_000,"truncated":false}),
    );
    drop(large);

    let cap_root = cwd.join("catalog-cap");
    for index in 0..16 {
        let name = format!("skill-{index}");
        write_skill(
            &cap_root,
            &name,
            &format!(
                "---\nname: {name}\ndescription: Valid cap fixture\nlicense: {}\n---\nSmall body.\n",
                "x".repeat(13_500)
            ),
        )?;
    }
    let cap = RuntimeRegistry::from_config(
        &support::config(&binary, &cap_root, &cap_root)?,
        cwd.clone(),
    )?;
    let result = bound(&cap)
        .execute(
            cwd.clone(),
            ToolCall::new("catalog-cap", "portable_skill_catalog", json!({})),
        )
        .await?;
    expected_error(
        &result,
        "catalog-cap",
        "catalog output exceeds 131072 bytes",
    )?;
    for index in 0..16 {
        let name = format!("skill-{index}");
        write_skill(
            &cap_root,
            &name,
            &format!(
                "---\nname: {name}\ndescription: Valid cap fixture\nlicense: {}\n---\nSmall body.\n",
                "x".repeat(1_000)
            ),
        )?;
    }
    let recovered = success(
        bound(&cap)
            .execute(
                cwd.clone(),
                ToolCall::new("catalog-after-cap", "portable_skill_catalog", json!({})),
            )
            .await?,
        "catalog-after-cap",
    )?;
    ensure!(
        recovered["catalog"]["skills"]
            .as_array()
            .is_some_and(|skills| skills.len() == 16),
        "same-registry catalog did not recover after reducing metadata"
    );
    ensure!(
        recovered["catalog"]["warnings"] == json!([]),
        "recovery silently skipped bad files"
    );
    check(
        &mut report,
        "catalog_module_cap_not_host_truncation",
        json!({"valid_files":16,"license_bytes_each":13_500,"error":result.error,"truncated":false,"same_registry_recovery":true}),
    );
    drop(cap);
    Ok(report)
}
