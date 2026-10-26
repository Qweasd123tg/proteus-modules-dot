mod common;

use anyhow::Result;
use common::Fixture;
use proteus_example_portable_skill_catalog::{
    CATALOG_TOOL, LOAD_TOOL, MODULE_ID, SkillTools,
    catalog::{TRUST_WARNING, discover, load_skill as checked_load_skill},
    config::{MAX_FILE_BYTES, Root},
    document::{parse, sha256, split_frontmatter},
    load, render_context,
};
use proteus_module_sdk::{
    contracts::{
        contracts::{
            ExecutionAttribution, ProcessComponentExportInitialize, ProcessModuleComposition,
            ProcessToolInvokeInput,
        },
        domain::{SkillRuntimeSettings, ToolCall, ToolSafety, new_call_id, new_execution_id},
        process_module::{ProcessModuleError, ToolModuleHost},
    },
    tool::ToolModule,
};
use serde_json::{Value, json};
use std::fs;

fn running() -> Result<bool> {
    Ok(false)
}
// Most tests hold source binding constant to isolate another invariant.
fn load_skill(
    config: &proteus_example_portable_skill_catalog::config::Config,
    disabled: &[String],
    id: &str,
    sha: &str,
    cancelled: impl FnMut() -> Result<bool>,
) -> Result<proteus_example_portable_skill_catalog::catalog::LoadedSkill> {
    let (root_id, name) = id.split_once(':').unwrap();
    let root = &config.roots.iter().find(|r| r.id == root_id).unwrap().path;
    let path = root.canonicalize().unwrap().join(name).join("SKILL.md");
    checked_load_skill(config, disabled, id, sha, &path, cancelled)
}

#[test]
fn provider_metadata_to_digest_bound_body_preserves_declared_requirements() {
    let f = Fixture::new();
    f.raw("review", "---\nname: review\ndescription: Review the change.\nlicense: MIT\ncompatibility: Requires a foreign binary not checked here.\nallowed-tools: Bash(git:*) Read\nmetadata:\n  author: 'пример'\n  version: '1'\n---\nUse references/check.md; no script is executed.");
    let s = discover(&f.config(), &[], running).unwrap();
    assert_eq!(s.skills.len(), 1);
    let skill = &s.skills[0];
    assert_eq!(skill.id, "project-agents:review");
    assert_eq!(skill.fields.license.as_deref(), Some("MIT"));
    assert_eq!(
        skill.fields.allowed_tools.as_deref(),
        Some("Bash(git:*) Read")
    );
    assert_eq!(skill.fields.metadata["author"], "пример");
    let loaded = load_skill(&f.config(), &[], &skill.id, &skill.sha256, running).unwrap();
    assert!(loaded.body.contains("references/check.md"));
    assert_eq!(loaded.skill.skill_directory, f.path.join("review"));
    assert_eq!(loaded.warning, TRUST_WARNING);
    let context = render_context(&s, 65_536).unwrap();
    assert!(context[0].content.starts_with(TRUST_WARNING));
    assert!(context[0].content.contains(&skill.sha256));
    assert!(
        !context[0].content.contains("Use references/check.md"),
        "body must not be in model-visible catalog"
    );
}

#[test]
fn same_name_in_explicit_roots_has_distinct_identity_without_shadowing() {
    let a = Fixture::new();
    let b = Fixture::new();
    a.skill("review", "A");
    b.skill("review", "B");
    let mut config = a.config();
    config.roots.push(Root {
        id: "user-claude".into(),
        path: b.path.clone(),
    });
    let s = discover(&config, &[], running).unwrap();
    assert_eq!(
        s.skills.iter().map(|s| s.id.as_str()).collect::<Vec<_>>(),
        ["project-agents:review", "user-claude:review"]
    );
    let selected = &s.skills[1];
    assert_eq!(
        load_skill(&config, &[], &selected.id, &selected.sha256, running)
            .unwrap()
            .body,
        "B"
    );
}

#[test]
fn duplicate_root_id_and_canonical_path_alias_are_config_errors() {
    let a = Fixture::new();
    let b = Fixture::new();
    let mut c = a.config();
    c.roots.push(Root {
        id: "project-agents".into(),
        path: b.path.clone(),
    });
    assert!(
        c.validate()
            .unwrap_err()
            .to_string()
            .contains("duplicate root id")
    );
    c.roots[1].id = "alias".into();
    c.roots[1].path = a.path.join(".");
    assert!(
        c.validate()
            .unwrap_err()
            .to_string()
            .contains("aliased root path")
    );
}

#[test]
fn disabled_existing_oversized_invalid_file_is_not_read_or_parsed() {
    let f = Fixture::new();
    let good = f.skill("good", "read this");
    f.raw("broken", &"not yaml".repeat(MAX_FILE_BYTES));
    let s = discover(&f.config(), &["project-agents:broken".into()], running).unwrap();
    assert_eq!(s.skills.len(), 1);
    assert_eq!(s.skipped_disabled, 1);
    assert!(s.warnings.is_empty());
    assert_eq!(s.read_bytes, fs::read(good).unwrap().len());
    let e = load_skill(
        &f.config(),
        &["project-agents:broken".into()],
        "project-agents:broken",
        &"0".repeat(64),
        running,
    )
    .unwrap_err();
    assert_eq!(e.to_string(), "skill is disabled");
}

#[test]
fn configured_disabled_id_is_applied_before_read() {
    let f = Fixture::new();
    f.raw("broken", "invalid");
    let mut c = f.config();
    c.disabled.insert("project-agents:broken".into());
    let s = discover(&c, &[], running).unwrap();
    assert_eq!(
        (s.read_bytes, s.skipped_disabled, s.warnings.len()),
        (0, 1, 0)
    );
}

#[test]
fn malformed_file_is_isolated_but_strict_mode_fails() {
    let f = Fixture::new();
    f.skill("good", "good");
    f.raw("bad", "not frontmatter");
    let s = discover(&f.config(), &[], running).unwrap();
    assert_eq!(s.skills.len(), 1);
    assert_eq!(s.warnings.len(), 1);
    assert!(s.warnings[0].contains("project-agents:bad"));
    let mut c = f.config();
    c.strict = true;
    assert!(
        discover(&c, &[], running)
            .unwrap_err()
            .to_string()
            .contains("opening YAML")
    );
}

#[test]
fn malformed_suffix_is_not_a_closing_fence_and_crlf_eof_is_supported() {
    assert!(split_frontmatter("---\nname: review\ndescription: hi---").is_err());
    assert!(parse("---\r\nname: review\r\ndescription: valid\r\n---", "review").is_ok());
    assert!(split_frontmatter("\u{feff}---\nname: review\n---").is_err());
}

#[test]
fn duplicate_known_or_metadata_keys_are_rejected() {
    assert!(
        parse(
            "---\nname: review\nname: review\ndescription: x\n---\nbody",
            "review"
        )
        .unwrap_err()
        .to_string()
        .contains("duplicate field `name`")
    );
    assert!(
        parse(
            "---\nname: review\ndescription: x\nmetadata:\n  source: one\n  source: two\n---\nbody",
            "review"
        )
        .unwrap_err()
        .to_string()
        .contains("duplicate metadata key")
    );
}

#[test]
fn unknown_frontmatter_extensions_fail_explicitly_and_do_not_execute() {
    assert!(
        parse(
            "---\nname: review\ndescription: x\nhooks:\n  command: arbitrary\n---\nbody",
            "review"
        )
        .is_err()
    );
}

#[test]
fn name_directory_mismatch_unicode_names_and_traversal_are_rejected() {
    assert!(parse("---\nname: other\ndescription: x\n---\nbody", "review").is_err());
    assert!(parse("---\nname: обзор\ndescription: x\n---\nbody", "обзор").is_err());
    let f = Fixture::new();
    assert!(
        load_skill(
            &f.config(),
            &[],
            "project-agents:../review",
            &"0".repeat(64),
            running
        )
        .is_err()
    );
}

#[test]
fn non_utf8_skill_file_is_isolated() {
    let f = Fixture::new();
    let path = f.skill("bad", "body");
    fs::write(path, [255, 254]).unwrap();
    f.skill("good", "body");
    let s = discover(&f.config(), &[], running).unwrap();
    assert_eq!(s.skills.len(), 1);
    assert!(s.warnings[0].contains("not UTF-8"));
}

#[test]
fn metadata_and_description_size_limits_are_explicit() {
    assert!(
        parse(
            &format!(
                "---\nname: review\ndescription: {}\n---\nbody",
                "x".repeat(1025)
            ),
            "review"
        )
        .is_err()
    );
    assert!(split_frontmatter(&format!("---\n{}\n---\nbody", "x".repeat(16_385))).is_err());
}

#[test]
fn entry_budget_includes_non_skills_and_precedes_parsing_in_that_root() {
    let f = Fixture::new();
    f.raw("one", "invalid");
    f.raw("two", "invalid");
    fs::write(f.path.join("README"), "not a skill").unwrap();
    let mut c = f.config();
    c.max_entries = 2;
    c.strict = true;
    assert!(
        discover(&c, &[], running)
            .unwrap_err()
            .to_string()
            .contains("entry budget")
    );
}

#[test]
fn per_file_exact_limit_is_valid_and_one_over_is_a_diagnostic() {
    let f = Fixture::new();
    let prefix = "---\nname: review\ndescription: valid\n---\n";
    f.raw(
        "review",
        &format!("{prefix}{}", "x".repeat(MAX_FILE_BYTES - prefix.len())),
    );
    assert_eq!(discover(&f.config(), &[], running).unwrap().skills.len(), 1);
    f.raw(
        "review",
        &format!("{prefix}{}", "x".repeat(MAX_FILE_BYTES - prefix.len() + 1)),
    );
    let s = discover(&f.config(), &[], running).unwrap();
    assert!(s.skills.is_empty());
    assert_eq!(s.read_bytes, MAX_FILE_BYTES + 1);
    assert!(s.warnings[0].contains("exceeds 131072"));
}

#[test]
fn aggregate_byte_budget_fails_whole_snapshot_even_in_lenient_mode() {
    let f = Fixture::new();
    let a = f.skill("a", "A");
    let b = f.skill("b", "B");
    let total = fs::read(a).unwrap().len() + fs::read(b).unwrap().len();
    let mut c = f.config();
    c.max_total_bytes = total;
    assert_eq!(discover(&c, &[], running).unwrap().read_bytes, total);
    c.max_total_bytes = total - 1;
    assert!(
        discover(&c, &[], running)
            .unwrap_err()
            .to_string()
            .contains("aggregate read byte budget")
    );
}

#[test]
fn skill_count_budget_never_returns_an_order_dependent_partial_catalog() {
    let f = Fixture::new();
    f.skill("a", "A");
    f.skill("b", "B");
    let mut c = f.config();
    c.max_skills = 1;
    assert!(
        discover(&c, &[], running)
            .unwrap_err()
            .to_string()
            .contains("skill count budget")
    );
}

#[test]
fn changed_body_with_unchanged_frontmatter_requires_refresh_and_new_digest() {
    let f = Fixture::new();
    f.skill("review", "old");
    let old = discover(&f.config(), &[], running)
        .unwrap()
        .skills
        .remove(0);
    f.skill("review", "new");
    assert!(
        load_skill(&f.config(), &[], &old.id, &old.sha256, running)
            .unwrap_err()
            .to_string()
            .contains("changed since catalog")
    );
    let fresh = discover(&f.config(), &[], running)
        .unwrap()
        .skills
        .remove(0);
    assert_ne!(fresh.sha256, old.sha256);
    assert_eq!(
        load_skill(&f.config(), &[], &fresh.id, &fresh.sha256, running)
            .unwrap()
            .body,
        "new"
    );
}

#[test]
fn absent_identity_and_wrong_digest_are_distinct_errors() {
    let f = Fixture::new();
    f.skill("review", "body");
    let absent = load_skill(
        &f.config(),
        &[],
        "project-agents:missing",
        &"0".repeat(64),
        running,
    )
    .unwrap_err();
    assert!(
        absent
            .to_string()
            .contains("cannot inspect skill directory")
    );
    let mismatch = load_skill(
        &f.config(),
        &[],
        "project-agents:review",
        &"0".repeat(64),
        running,
    )
    .unwrap_err();
    assert!(mismatch.to_string().contains("changed since catalog"));
    assert!(
        load_skill(
            &f.config(),
            &[],
            "project-agents:review",
            "not-a-sha",
            running
        )
        .unwrap_err()
        .to_string()
        .contains("64 lowercase")
    );
}

#[test]
fn disable_model_invocation_hides_and_blocks_even_with_correct_digest() {
    let f = Fixture::new();
    let text = "---\nname: review\ndescription: x\ndisable-model-invocation: true\n---\nbody";
    f.raw("review", text);
    assert!(
        discover(&f.config(), &[], running)
            .unwrap()
            .skills
            .is_empty()
    );
    assert!(
        load_skill(
            &f.config(),
            &[],
            "project-agents:review",
            &sha256(text.as_bytes()),
            running
        )
        .unwrap_err()
        .to_string()
        .contains("disables model")
    );
}

#[test]
fn user_invocable_hint_is_preserved_not_converted_to_model_permission() {
    let f = Fixture::new();
    f.raw(
        "review",
        "---\nname: review\ndescription: x\nuser-invocable: false\n---\nbody",
    );
    let s = discover(&f.config(), &[], running).unwrap();
    assert_eq!(s.skills[0].fields.user_invocable, Some(false));
}

#[test]
fn cancelled_or_failed_cancellation_checks_never_become_lenient_success() {
    let f = Fixture::new();
    f.skill("review", "body");
    assert!(
        discover(&f.config(), &[], || Ok(true))
            .unwrap_err()
            .to_string()
            .contains("canceled")
    );
    // A one-shot failure deep in file reading must not be swallowed by the next
    // successful check or reclassified as a bad-file warning.
    let mut checks = 0;
    let error = discover(&f.config(), &[], || {
        checks += 1;
        if checks == 8 {
            anyhow::bail!("synthetic callback failure")
        }
        Ok(false)
    })
    .unwrap_err();
    assert!(error.to_string().contains("cancellation check failed"));
}

#[test]
fn rendered_context_budget_counts_actual_utf8_and_fixed_source_envelope() {
    let f = Fixture::new();
    f.skill("review", "body");
    let s = discover(&f.config(), &[], running).unwrap();
    let chunk = render_context(&s, 65_536).unwrap().remove(0);
    let exact = format!("Context from {MODULE_ID}:\n{}", chunk.content).len();
    assert!(render_context(&s, exact).is_ok());
    assert!(render_context(&s, exact - 1).is_err());
}

#[cfg(unix)]
#[test]
fn symlink_directory_file_and_root_are_not_followed() {
    use std::os::unix::fs::symlink;
    let f = Fixture::new();
    let outside = Fixture::new();
    outside.skill("review", "outside");
    symlink(outside.path.join("review"), f.path.join("review")).unwrap();
    let s = discover(&f.config(), &[], running).unwrap();
    assert!(s.skills.is_empty());
    assert!(s.warnings[0].contains("symlink"));
    fs::remove_file(f.path.join("review")).unwrap();
    fs::create_dir(f.path.join("review")).unwrap();
    symlink(
        outside.path.join("review/SKILL.md"),
        f.path.join("review/SKILL.md"),
    )
    .unwrap();
    assert!(
        discover(&f.config(), &[], running)
            .unwrap()
            .skills
            .is_empty()
    );
    let link = f.path.join("root-link");
    symlink(&outside.path, &link).unwrap();
    let mut c = f.config();
    c.roots[0].path = link;
    let s = discover(&c, &[], running).unwrap();
    assert!(s.skills.is_empty());
    assert!(s.warnings[0].contains("root must be"));
}

struct NoCallbacks;
impl ToolModuleHost for NoCallbacks {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
}
fn invoke(
    tools: &SkillTools,
    name: &str,
    args: Value,
) -> proteus_module_sdk::contracts::domain::ToolResult {
    tools
        .invoke(
            ProcessToolInvokeInput {
                call: ToolCall::new(new_call_id(), name, args),
                cwd: "/irrelevant-request-cwd".into(),
                attribution: ExecutionAttribution::detached(new_execution_id()),
                skills: SkillRuntimeSettings::default(),
            },
            &mut NoCallbacks,
        )
        .unwrap()
}

#[test]
fn actual_tool_contract_refresh_load_error_identity_and_safety() {
    let f = Fixture::new();
    f.skill("review", "body");
    let tools = SkillTools { config: f.config() };
    assert!(
        tools
            .definitions()
            .iter()
            .all(|d| d.spec.safety == ToolSafety::ReadOnly)
    );
    let list = invoke(&tools, CATALOG_TOOL, json!({}));
    assert!(list.ok);
    assert_eq!(list.metadata["tool"], CATALOG_TOOL);
    let data: Value = serde_json::from_str(&list.output).unwrap();
    let entry = &data["catalog"]["skills"][0];
    let loaded = invoke(
        &tools,
        LOAD_TOOL,
        json!({"id":entry["id"],"sha256":entry["sha256"],"catalog_path":entry["path"]}),
    );
    assert!(loaded.ok);
    assert_eq!(loaded.metadata["hints_grant_authority"], false);
    let error = invoke(
        &tools,
        LOAD_TOOL,
        json!({"id":entry["id"],"sha256":"0".repeat(64),"catalog_path":entry["path"]}),
    );
    assert!(!error.ok);
    assert!(error.output.is_empty());
    assert!(error.error.unwrap().contains("changed since catalog"));
}

#[test]
fn module_binding_rejects_wrong_identity_slot_version_and_composition() {
    let f = Fixture::new();
    let config = serde_json::to_value(f.config()).unwrap();
    let good = ProcessComponentExportInitialize::new(
        "context_provider",
        MODULE_ID,
        "v4",
        ProcessModuleComposition::OrderedMany,
        config,
        Vec::<String>::new(),
    );
    assert!(load(good.clone()).is_ok());
    let mut bad = good.clone();
    bad.module_id = "foreign".into();
    assert!(load(bad).is_err());
    let mut bad = good.clone();
    bad.contract_version = "v3".into();
    assert!(load(bad).is_err());
    let mut bad = good;
    bad.composition = ProcessModuleComposition::SelectOne;
    assert!(load(bad).is_err());
}

#[test]
fn identical_bytes_from_different_roots_do_not_satisfy_catalog_source_binding() {
    let provider = Fixture::new();
    let tool = Fixture::new();
    provider.skill("review", "Read references/check.md");
    tool.skill("review", "Read references/check.md");
    let advertised = discover(&provider.config(), &[], running)
        .unwrap()
        .skills
        .remove(0);
    let actual = discover(&tool.config(), &[], running)
        .unwrap()
        .skills
        .remove(0);
    assert_eq!(advertised.sha256, actual.sha256);
    assert_ne!(advertised.path, actual.path);
    let error = checked_load_skill(
        &tool.config(),
        &[],
        &advertised.id,
        &advertised.sha256,
        &advertised.path,
        running,
    )
    .unwrap_err();
    assert!(
        error
            .to_string()
            .contains("source differs from catalog_path")
    );
    assert!(
        checked_load_skill(
            &tool.config(),
            &[],
            &actual.id,
            &actual.sha256,
            &actual.path,
            running
        )
        .is_ok()
    );
}

#[test]
fn valid_file_with_escaping_exceeds_tool_text_bound_before_host_truncation() {
    let f = Fixture::new();
    f.skill("review", &"\\".repeat(100_000));
    let skill = discover(&f.config(), &[], running)
        .unwrap()
        .skills
        .remove(0);
    let tools = SkillTools { config: f.config() };
    let result = invoke(
        &tools,
        LOAD_TOOL,
        json!({"id":skill.id,"sha256":skill.sha256,"catalog_path":skill.path}),
    );
    assert!(!result.ok);
    assert!(
        result
            .error
            .as_deref()
            .unwrap()
            .contains("skill output exceeds 131072")
    );
    assert!(serde_json::to_vec(&result).unwrap().len() < 262_144);
}

#[test]
fn escaping_heavy_output_below_limit_remains_complete_json() {
    let f = Fixture::new();
    let body = "\"".repeat(60_000);
    f.skill("review", &body);
    let skill = discover(&f.config(), &[], running)
        .unwrap()
        .skills
        .remove(0);
    let tools = SkillTools { config: f.config() };
    let result = invoke(
        &tools,
        LOAD_TOOL,
        json!({"id":skill.id,"sha256":skill.sha256,"catalog_path":skill.path}),
    );
    assert!(result.ok, "{result:?}");
    assert!(result.output.len() <= 131_072);
    assert_eq!(
        serde_json::from_str::<Value>(&result.output).unwrap()["body"],
        body
    );
}

#[test]
fn reachable_catalog_text_exceeds_default_host_cap_without_exceeding_wire_cap() {
    let f = Fixture::new();
    for number in 0..16 {
        let name = format!("skill-{number}");
        f.raw(&name, &format!("---\nname: {name}\ndescription: Valid metadata-only catalogue fixture.\nlicense: {}\n---\nbody", "x".repeat(13_500)));
    }
    let snapshot = discover(&f.config(), &[], running).unwrap();
    assert_eq!(snapshot.skills.len(), 16);
    let raw_payload =
        serde_json::to_string(&json!({"warning":TRUST_WARNING,"catalog":snapshot})).unwrap();
    assert!(
        raw_payload.len() > 200_000,
        "would exceed pinned default host text cap"
    );
    let outer = proteus_module_sdk::contracts::domain::ToolResult::ok(new_call_id(), raw_payload)
        .with_metadata(json!({"tool":CATALOG_TOOL,"provider":MODULE_ID,"read_only":true,"hints_grant_authority":false}));
    assert!(
        serde_json::to_vec(&outer).unwrap().len() < 262_144,
        "old outer cap alone would permit this reachable catalog"
    );
    let result = invoke(&SkillTools { config: f.config() }, CATALOG_TOOL, json!({}));
    assert!(!result.ok);
    assert_eq!(
        result.error.as_deref(),
        Some("catalog output exceeds 131072 bytes")
    );
    assert!(result.output.is_empty());
}
