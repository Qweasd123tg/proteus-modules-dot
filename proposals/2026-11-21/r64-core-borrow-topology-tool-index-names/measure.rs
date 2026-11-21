mod candidate;
mod stock;
mod test_alloc;

mod core {
    pub use proteus_core::core::AppConfig;

    pub mod agent_control {
        use crate::contracts::ToolSource;
        include!("ownership.rs");
    }
}

pub use proteus_contracts::{contracts, domain};

use contracts::{ProcessToolOwner, ToolSource};
use core::AppConfig;
use domain::{ToolSafety, ToolSpec};
use proteus_contracts::app_protocol::topology::{ToolTopology, TopologyWarning};
use serde_json::json;
use std::{hint::black_box, io::Write as _};

type Registry = Vec<(ToolSource, ToolSpec)>;

fn spec(name: &str, i: usize) -> ToolSpec {
    ToolSpec::new(
        name,
        format!("inspect fixture {i}"),
        json!({"type":"object","properties":{"item":{"type":"string"}}}),
        match i % 5 {
            0 => ToolSafety::ReadOnly,
            1 => ToolSafety::WritesFiles,
            2 => ToolSafety::RunsCommands,
            3 => ToolSafety::Network,
            _ => ToolSafety::Dangerous,
        },
    )
}

fn source(i: usize) -> ToolSource {
    match i % 7 {
        0 => ToolSource::builtin("core"),
        1 => ToolSource::builtin("agent-control-task"),
        2 => ToolSource::builtin("agent-control-collaboration"),
        3 => ToolSource::ProviderHosted {
            provider: "fixture".into(),
        },
        4 => ToolSource::Mcp {
            server: "fixture".into(),
        },
        5 => ToolSource::Process {
            owner: ProcessToolOwner {
                component_id: "fixture".into(),
                module_id: "demo".into(),
            },
        },
        _ => ToolSource::Dynamic {
            origin: "fixture".into(),
        },
    }
}

fn fixture(registered_count: usize, configured_count: usize) -> (AppConfig, Registry) {
    let mut config = AppConfig::default();
    config.tools.enabled = (0..configured_count)
        .rev()
        .map(|id| format!("tool-{id:03}"))
        .collect();
    let registry = (0..registered_count)
        .rev()
        .map(|i| (source(i), spec(&format!("tool-{i:03}"), i)))
        .collect();
    (config, registry)
}

fn edge_fixture() -> (AppConfig, Registry) {
    let mut config = AppConfig::default();
    config.tools.enabled = [
        "z", "same", "same", "Å", "a", "", "e\u{301}", "e\u{301}", "😀",
    ]
    .map(str::to_owned)
    .to_vec();
    let registry = vec![
        (source(0), spec("same", 0)),
        (source(4), spec("mcp-only", 1)),
        (source(5), spec("same", 2)),
        (source(0), spec("not-enabled", 3)),
        (source(2), spec("agent", 4)),
        (source(0), spec("", 5)),
        (source(6), spec("😀", 3)),
    ];
    (config, registry)
}

#[test]
fn sorted_deduplicated_warnings_and_stable_tool_ties() {
    let (config, registry) = edge_fixture();
    let mut warnings = vec![TopologyWarning::error("existing")];
    let actual = candidate::build_tools(&config, &registry, &mut warnings);
    assert_eq!(warnings[0], TopologyWarning::error("existing"));
    assert_eq!(
        warnings[1..]
            .iter()
            .map(|w| w.message.as_str())
            .collect::<Vec<_>>(),
        ["a", "e\u{301}", "z", "Å"].map(|name| format!(
            "tools.enabled contains {name}, but no registered tool provides it"
        ))
    );
    assert!(actual.windows(2).all(|pair| pair[0].name <= pair[1].name));
    let same = actual
        .iter()
        .filter(|tool| tool.name == "same")
        .collect::<Vec<_>>();
    assert_eq!(same.len(), 2);
    assert_eq!(same[0].source, "builtin:core");
    assert_eq!(same[1].source, "process:fixture/demo");
    assert_eq!(same[1].owner.as_ref().unwrap().module_id, "demo");
    assert!(same.iter().all(|tool| tool.enabled && tool.registered));
    assert!(
        actual
            .iter()
            .any(|tool| tool.name == "mcp-only" && tool.enabled && tool.runtime_managed)
    );
    assert!(
        actual
            .iter()
            .any(|tool| tool.name == "not-enabled" && !tool.enabled && !tool.runtime_managed)
    );
}

#[test]
fn exact_sorted_rows_warnings_and_schema_bytes() {
    let file = std::fs::File::create(std::env::var_os("R64_SNAPSHOT").unwrap()).unwrap();
    let mut out = std::io::BufWriter::new(file);
    let inputs = [
        fixture(0, 0),
        fixture(16, 16),
        edge_fixture(),
        fixture(64, 80),
    ];
    let generated = (0..192).map(|i| {
        let (mut config, mut registry) = fixture(i % 24, i % 35);
        if i % 3 == 0 {
            config
                .tools
                .enabled
                .extend(["".to_owned(), "é 😀".to_owned(), "é 😀".to_owned()]);
        }
        if i % 4 == 0 {
            registry.push((source(i), spec("é 😀", i)));
        }
        if i % 5 == 0 {
            registry.reverse();
        }
        (config, registry)
    });
    let mut count = 0;
    for (config, registry) in inputs.into_iter().chain(generated) {
        let mut old_warnings = vec![TopologyWarning::warn("seeded")];
        let mut new_warnings = old_warnings.clone();
        let old = stock::build_tools(&config, &registry, &mut old_warnings);
        let new = candidate::build_tools(&config, &registry, &mut new_warnings);
        let actual = serde_json::to_vec(&(new, new_warnings)).unwrap();
        assert_eq!(
            serde_json::to_vec(&(old, old_warnings)).unwrap(),
            actual,
            "fixture {count}"
        );
        out.write_all(&(actual.len() as u64).to_le_bytes()).unwrap();
        out.write_all(&actual).unwrap();
        count += 1;
    }
    out.flush().unwrap();
    assert_eq!(count, 196);
    println!("{count} byte-identical tool rows and warning payloads");
}

#[test]
fn borrowed_indexes_remove_name_allocations() {
    for (case, (config, registry)) in [
        ("empty", fixture(0, 0)),
        ("ordinary-16", fixture(16, 16)),
        ("duplicates-and-unicode", edge_fixture()),
        ("64-tools-16-missing", fixture(64, 80)),
    ] {
        let mut baseline_warnings = vec![];
        let mut candidate_warnings = vec![];
        let (stock, old) = test_alloc::measure(|| {
            black_box(stock::build_tools(
                black_box(&config),
                black_box(&registry),
                black_box(&mut baseline_warnings),
            ))
        });
        let (next, new) = test_alloc::measure(|| {
            black_box(candidate::build_tools(
                black_box(&config),
                black_box(&registry),
                black_box(&mut candidate_warnings),
            ))
        });
        assert_eq!(stock, next);
        assert_eq!(baseline_warnings, candidate_warnings);
        assert!(new.calls <= old.calls && new.bytes <= old.bytes, "{case}");
        if !registry.is_empty() {
            assert!(new.calls < old.calls && new.bytes < old.bytes, "{case}");
        }
        println!(
            "{case:24} alloc/realloc {:4} -> {:4}; requested bytes {:7} -> {:7}",
            old.calls, new.calls, old.bytes, new.bytes
        );
    }
}
