//! Authored small same-input budget pairs against checksum-pinned serde-saphyr2.0.0.
use std::{cell::RefCell, io::Cursor, rc::Rc};

use anyhow::{Context, Result, bail, ensure};
use serde_json::{Value, json};
use serde_saphyr::{Budget, Error, Options, budget::BudgetBreach};

use crate::{CORPUS, accepted, document, emit, rejected};

pub fn run(kind: &str, mode: &str) -> Result<()> {
    ensure!(
        matches!(mode, "permissive" | "restrictive" | "comments_disabled"),
        "unknown budget mode"
    );
    ensure!(
        mode != "comments_disabled" || kind == "comments",
        "disabled-comment mode only applies to comments"
    );
    let (case_id, field, low, high, expected_kind) = match kind {
        "depth" => ("quoted_metadata_scalar", "max_depth", 1, 4, "Depth"),
        "nodes" => ("plain_valid", "max_nodes", 1, 256, "Nodes"),
        "events" => ("plain_valid", "max_events", 1, 256, "Events"),
        "scalar_bytes" => (
            "unicode_scalar",
            "max_total_scalar_bytes",
            1,
            65_536,
            "ScalarBytes",
        ),
        "aliases" => ("alias_string", "max_aliases", 0, 8, "Aliases"),
        "comments" => (
            "raw_bytes_16384",
            "max_total_comment_bytes",
            1,
            65_536,
            "CommentBytes",
        ),
        "reader_bytes" => (
            "plain_valid",
            "max_reader_input_bytes",
            1,
            65_536,
            "ReaderInputBytes",
        ),
        _ => bail!("unknown budget kind"),
    };
    let corpus: Value = serde_json::from_str(CORPUS)?;
    let case = corpus["cases"]
        .as_array()
        .context("invalid corpus")?
        .iter()
        .find(|case| case["id"] == case_id)
        .context("missing budget case")?;
    let yaml = case["yaml"].as_str().context("missing budget YAML")?;
    ensure!(
        yaml.len() <= 16_385 && case["yaml_sha256"] == document::sha256(yaml.as_bytes()),
        "budget input changed"
    );
    let limit = if mode == "permissive" { high } else { low };
    let mut budget = Budget::default();
    match kind {
        "depth" => budget.max_depth = limit,
        "nodes" => budget.max_nodes = limit,
        "events" => budget.max_events = limit,
        "scalar_bytes" => budget.max_total_scalar_bytes = limit,
        "aliases" => budget.max_aliases = limit,
        "comments" => budget.max_total_comment_bytes = limit,
        "reader_bytes" => budget.max_reader_input_bytes = Some(limit),
        _ => bail!("unknown configured budget"),
    }
    let mut options = Options::default();
    options.budget = Some(budget);
    if mode == "comments_disabled" {
        options.emit_comments = false;
    }
    let configured_debug = format!("{options:?}");
    let reports = Rc::new(RefCell::new(Vec::<Value>::new()));
    let callback_reports = Rc::clone(&reports);
    let options = options.with_budget_report(move |report| {
        callback_reports.borrow_mut().push(json!({"breached":report.breached.as_ref().map(breach_kind),
            "events":report.events,"aliases":report.aliases,"anchors":report.anchors,
            "documents":report.documents,"nodes":report.nodes,"max_depth":report.max_depth,
            "total_scalar_bytes":report.total_scalar_bytes,"total_comment_bytes":report.total_comment_bytes,
            "recorded_anchor_events":report.recorded_anchor_events,"recorded_anchor_bytes":report.recorded_anchor_bytes}));
    });
    let parsed = if kind == "reader_bytes" {
        serde_saphyr::from_reader_with_options::<_, document::Frontmatter>(
            Cursor::new(yaml.as_bytes()),
            options,
        )
    } else {
        serde_saphyr::from_str_with_options::<document::Frontmatter>(yaml, options)
    };
    let (outcome, classification) = match parsed {
        Ok(fields) => (accepted(fields, None)?, None),
        Err(error) => (rejected(&error), classify(&error)),
    };
    let reports = reports.borrow().clone();
    emit(
        json!({"schema_version":1,"parser":"serde_saphyr_budget","kind":kind,"mode":mode,
        "case_id":case_id,"yaml_sha256":case["yaml_sha256"],"raw_yaml_bytes":yaml.len(),
        "entrypoint":if kind == "reader_bytes" {"typed Frontmatter from_reader_with_options over authored in-memory Cursor"} else {"typed Frontmatter from_str_with_options"},
        "limit_field":field,"limit":limit,"expected_restrictive_kind":expected_kind,
        "options_profile":{"base":"Options::default; one budget field overridden","configured_debug":configured_debug,
            "emit_comments":mode != "comments_disabled","features":["deserialize","comments"],
            "include_or_property_resolver_installed":false},
        "outcome":outcome,"typed_error_classification":classification,"budget_reports":reports,
        "not_claimed":"migration acceptance, RSS/CPU bound, or reader-limit coverage on the from_str path"}),
    )
}

fn breach_kind(breach: &BudgetBreach) -> &'static str {
    match breach {
        BudgetBreach::Depth { .. } => "Depth",
        BudgetBreach::Nodes { .. } => "Nodes",
        BudgetBreach::Events { .. } => "Events",
        BudgetBreach::ScalarBytes { .. } => "ScalarBytes",
        BudgetBreach::Aliases { .. } => "Aliases",
        BudgetBreach::CommentBytes { .. } => "CommentBytes",
        // InputBytes is not accepted as the reader control: pinned source maps
        // scanner input-byte rejection to the specific IOError/FileTooLarge path.
        _ => "OtherBudgetBreach",
    }
}

fn classify(error: &Error) -> Option<&'static str> {
    let mut current = error;
    while let Error::WithSnippet { error, .. } | Error::AliasError { error, .. } = current {
        current = error.as_ref();
    }
    match current {
        Error::Budget { breach, .. } => Some(breach_kind(breach)),
        Error::IOError { cause } if cause.kind() == std::io::ErrorKind::FileTooLarge => {
            Some("ReaderInputBytes")
        }
        _ => None,
    }
}
