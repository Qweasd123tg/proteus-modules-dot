//! Authored typed parser comparison against checksum-pinned registry sources.
mod budgets;
#[allow(dead_code)]
#[path = "frozen/config.rs"]
mod config;
#[allow(dead_code)]
#[path = "frozen/document.rs"]
mod document;

use anyhow::{Context, Result, bail, ensure};
use document::Frontmatter;
use serde_json::{Value, json};

const CORPUS: &str = include_str!("../fixtures/corpus.json");
const ENVELOPES: &str = include_str!("../fixtures/envelopes.json");
const BODY: &str = "Authored parser comparison body.";

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().is_some_and(|arg| arg == "saphyr_budget") {
        ensure!(args.len() == 3, "usage: comparison saphyr_budget KIND MODE");
        return budgets::run(&args[1], &args[2]);
    }
    ensure!(args.len() == 2, "usage: comparison PARSER CASE_ID");
    let parser = args[0].as_str();
    if parser == "baseline_envelope" {
        return envelope(&args[1]);
    }
    ensure!(
        matches!(
            parser,
            "baseline_typed" | "baseline_module" | "yaml_serde" | "serde_saphyr"
        ),
        "unknown parser selection"
    );
    let corpus: Value = serde_json::from_str(CORPUS)?;
    let cases = corpus["cases"]
        .as_array()
        .context("invalid authored corpus")?;
    ensure!(cases.len() == 38, "authored corpus count changed");
    let matching: Vec<_> = cases.iter().filter(|case| case["id"] == args[1]).collect();
    ensure!(matching.len() == 1, "expected one exact authored case ID");
    let case = matching[0];
    let yaml = case["yaml"].as_str().context("missing authored YAML")?;
    let directory = case["directory"].as_str().context("missing directory")?;
    ensure!(
        yaml.len() <= 16_385,
        "authored corpus raw-byte cap exceeded"
    );
    ensure!(
        case["yaml_utf8_bytes"] == yaml.len(),
        "corpus byte length drift"
    );
    ensure!(
        case["yaml_sha256"] == document::sha256(yaml.as_bytes()),
        "corpus digest drift"
    );
    let outcome = match parser {
        "baseline_typed" => match serde_yaml::from_str::<Frontmatter>(yaml) {
            Ok(fields) => accepted(fields, None)?,
            Err(error) => rejected(&error),
        },
        "baseline_module" => {
            let full = format!("---\n{yaml}---\n{BODY}\n");
            match document::parse(&full, directory) {
                Ok((fields, body)) => accepted(fields, Some(body))?,
                Err(error) => json!({"status":"rejected","display":format!("{error:#}"),
                    "debug":format!("{error:?}"),"classification":"not_normalized"}),
            }
        }
        "yaml_serde" => match yaml_serde::from_str::<Frontmatter>(yaml) {
            Ok(fields) => accepted(fields, None)?,
            Err(error) => rejected(&error),
        },
        "serde_saphyr" => match serde_saphyr::from_str::<Frontmatter>(yaml) {
            Ok(fields) => accepted(fields, None)?,
            Err(error) => rejected(&error),
        },
        _ => bail!("unsupported parser selection"),
    };
    let result = json!({"schema_version":1,"parser":parser,"case_id":args[1],
        "entrypoint":if parser == "baseline_module" {"frozen module parse"} else {"direct typed Frontmatter from_str"},
        "yaml_sha256":case["yaml_sha256"],"raw_yaml_bytes":yaml.len(),"outcome":outcome,
        "options_profile":if parser == "serde_saphyr" {json!({"selection":"Options::default via from_str",
            "debug":format!("{:?}",serde_saphyr::Options::default()),"features":["deserialize","comments"],
            "include_or_property_resolver_installed":false})} else {json!({"selection":"library default; no configurable budget API selected"})},
        "not_claimed":"migration acceptance, complete portable module, Core, or parser resource-budget proof"});
    emit(result)
}

fn emit(result: Value) -> Result<()> {
    let serialized = serde_json::to_string(&result)?;
    ensure!(
        serialized.len() <= 131_072,
        "observation output exceeds 128 KiB"
    );
    println!("{serialized}");
    Ok(())
}

fn envelope(id: &str) -> Result<()> {
    let corpus: Value = serde_json::from_str(ENVELOPES)?;
    let cases = corpus["cases"]
        .as_array()
        .context("invalid envelope corpus")?;
    ensure!(cases.len() == 7, "envelope corpus count changed");
    let matching: Vec<_> = cases.iter().filter(|case| case["id"] == id).collect();
    ensure!(matching.len() == 1, "expected exact envelope control ID");
    let case = matching[0];
    let text = case["document"]
        .as_str()
        .context("missing envelope document")?;
    let directory = case["directory"]
        .as_str()
        .context("missing envelope directory")?;
    ensure!(
        case["document_utf8_bytes"] == text.len(),
        "envelope length drift"
    );
    ensure!(
        case["document_sha256"] == document::sha256(text.as_bytes()),
        "envelope digest drift"
    );
    let outcome = match document::parse(text, directory) {
        Ok((fields, body)) => accepted(fields, Some(body))?,
        Err(error) => json!({"status":"rejected","display":format!("{error:#}"),
            "debug":format!("{error:?}"),"classification":"not_normalized"}),
    };
    emit(
        json!({"schema_version":1,"parser":"baseline_envelope","case_id":id,
        "entrypoint":"frozen document::parse envelope control","document_sha256":case["document_sha256"],
        "raw_document_bytes":text.len(),"outcome":outcome,
        "not_claimed":"candidate parser compatibility or complete portable module execution"}),
    )
}

fn accepted(fields: Frontmatter, body: Option<String>) -> Result<Value> {
    let serialized = serde_json::to_vec(&fields)?;
    Ok(
        json!({"status":"accepted","fields":fields,"serialized_fields_bytes":serialized.len(),"body":body}),
    )
}

fn rejected(error: &(impl std::fmt::Display + std::fmt::Debug)) -> Value {
    json!({"status":"rejected","display":error.to_string(),"debug":format!("{error:?}"),
        "classification":"not_normalized"})
}
