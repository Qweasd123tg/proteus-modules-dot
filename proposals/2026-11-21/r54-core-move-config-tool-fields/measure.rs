use super::*;
use crate::{
    contracts::ProcessToolOwner,
    domain::{ToolSafety, ToolSpec},
    r54_alloc::measure,
};
use serde_json::json;

fn tools(n: usize, long: bool) -> Vec<(ToolSource, ToolSpec)> {
    (0..n)
        .map(|i| {
            let source = match i % 5 {
                0 => ToolSource::Process {
                    owner: ProcessToolOwner {
                        component_id: "file-tools".into(),
                        module_id: "files.find".into(),
                    },
                },
                1 => ToolSource::Mcp {
                    server: "fixture & 🧪".into(),
                },
                2 => ToolSource::builtin("core"),
                3 => ToolSource::ProviderHosted {
                    provider: "offline".into(),
                },
                _ => ToolSource::Dynamic {
                    origin: "example".into(),
                },
            };
            let base = match i % 5 {
                0 => "Find entries by name; newest first.",
                1 => "Сводка; сохранить порядок 🌍\r\nвторая строка\n",
                2 => "",
                3 => "  retained spaces and \t tabs  ",
                _ => "control \0 and newline\n\n",
            };
            let desc = if long {
                base.repeat(61)
            } else {
                base.to_owned()
            };
            let safety = match i % 5 {
                0 => ToolSafety::ReadOnly,
                1 => ToolSafety::WritesFiles,
                2 => ToolSafety::RunsCommands,
                3 => ToolSafety::Network,
                _ => ToolSafety::Dangerous,
            };
            (
                source,
                ToolSpec::new(
                    format!("module_tool_{i:03}"),
                    desc,
                    json!({"type":"object"}),
                    safety,
                ),
            )
        })
        .collect()
}

#[test]
fn r54_paired_registered_tool_projection() {
    let mut snapshots = Vec::new();
    for (case, n, long, capacity) in [
        ("none", 0, false, "tight"),
        ("one", 1, false, "tight"),
        ("five", 5, false, "tight"),
        ("ordinary", 24, false, "natural"),
        ("many", 128, false, "tight"),
        ("multiline", 22, true, "tight"),
        ("oversized", 24, false, "oversized"),
    ] {
        let mut source = tools(n, long);
        for (i, (_, spec)) in source.iter_mut().enumerate() {
            spec.supports_parallel_tool_calls = i % 2 == 0;
            if capacity == "tight" {
                spec.name.shrink_to_fit();
                spec.description.shrink_to_fit();
            } else if capacity == "oversized" {
                spec.name.reserve_exact(128);
                spec.description.reserve_exact(1024);
            }
        }
        let saved_bytes = source
            .iter()
            .map(|(_, spec)| [&spec.name, &spec.description])
            .flatten()
            .filter(|v| v.len() == v.capacity())
            .map(|v| v.len())
            .sum::<usize>();
        let saved_calls = source
            .iter()
            .map(|(_, spec)| [&spec.name, &spec.description])
            .flatten()
            .filter(|v| !v.is_empty() && v.len() == v.capacity())
            .count();
        let (old, a) = measure(|| stock_registered_tool_summaries(&source));
        let (new, b) = measure(|| registered_tool_summaries(source));
        let old_wire = serde_json::to_vec(&old).unwrap();
        let new_wire = serde_json::to_vec(&new).unwrap();
        assert_eq!(old_wire, new_wire, "{case}: serialized DTO differs");
        assert_eq!(
            old.capacity(),
            new.capacity(),
            "{case}: retained vector capacity"
        );
        assert_eq!(a.calls - b.calls, saved_calls, "{case}: calls");
        assert_eq!(a.bytes - b.bytes, saved_bytes, "{case}: bytes");
        for (old, new) in old.iter().zip(&new) {
            assert_eq!(
                old.name.capacity(),
                new.name.capacity(),
                "{case}: retained name capacity"
            );
            assert_eq!(
                old.description.capacity(),
                new.description.capacity(),
                "{case}: retained description capacity"
            );
        }
        println!(
            "r54 {case}: calls {}->{}, bytes {}->{}",
            a.calls, b.calls, a.bytes, b.bytes
        );
        snapshots.push(json!([case, new]));
    }
    let snapshot = std::env::var("R54_SUMMARY_PROBE_SNAPSHOT").unwrap();
    std::fs::write(snapshot, serde_json::to_vec(&snapshots).unwrap()).unwrap();
}
