mod core {
    pub use proteus_contracts::app_protocol::topology::*;
}

#[path = "candidate/crates/proteus-core/src/core/topology_render/mod.rs"]
mod candidate;
#[path = "stock/mod.rs"]
mod stock;
mod test_alloc;

use core::{
    ModelTopology, ModuleSourceTopology, ModuleTopology, SlotTopology, ToolTopology, TopologyEdge,
    TopologySnapshot, TopologyWarning,
};
use std::{hint::black_box, io::Write as _};

type Renderer = fn(&TopologySnapshot) -> String;
const RENDERERS: [(&str, Renderer, Renderer); 6] = [
    (
        "table",
        stock::render_topology_table,
        candidate::render_topology_table,
    ),
    (
        "map",
        stock::render_topology_map,
        candidate::render_topology_map,
    ),
    (
        "path",
        stock::render_topology_runtime_path,
        candidate::render_topology_runtime_path,
    ),
    (
        "markdown",
        stock::render_topology_markdown,
        candidate::render_topology_markdown,
    ),
    (
        "runtime-mermaid",
        stock::render_topology_runtime_mermaid,
        candidate::render_topology_runtime_mermaid,
    ),
    (
        "full-mermaid",
        stock::render_topology_mermaid,
        candidate::render_topology_mermaid,
    ),
];

fn typical(tools: usize) -> TopologySnapshot {
    let mut snapshot = TopologySnapshot {
        profile: "fixture".into(),
        cwd: "/fixture/utf8".into(),
        config_path: Some("/fixture/config.toml".into()),
        config_files: vec!["/fixture/config.toml".into()],
        module_epoch: 7,
        permission_mode: "workspace-write".into(),
        model: Some(ModelTopology {
            provider: "fixture".into(),
            name: "small-model".into(),
            stream: true,
        }),
        hooks: vec!["before-context".into(), "after-turn".into()],
        ..Default::default()
    };
    let rows = [
        (
            "workflow",
            "turn",
            "orchestrator",
            10,
            ModuleSourceTopology::Process,
        ),
        (
            "context",
            "context",
            "pipeline",
            20,
            ModuleSourceTopology::Builtin,
        ),
        (
            "hook",
            "chain",
            "pipeline",
            25,
            ModuleSourceTopology::Process,
        ),
        ("model", "llm", "pipeline", 30, ModuleSourceTopology::Config),
        (
            "policy",
            "approve",
            "pipeline",
            40,
            ModuleSourceTopology::Unknown,
        ),
        (
            "tools",
            "registry",
            "registry",
            45,
            ModuleSourceTopology::Builtin,
        ),
        (
            "storage",
            "sqlite",
            "backend",
            50,
            ModuleSourceTopology::Process,
        ),
        (
            "renderer",
            "plain",
            "post_turn",
            60,
            ModuleSourceTopology::Process,
        ),
    ];
    for (id, module, category, order, source) in rows.into_iter().rev() {
        snapshot.slots.push(SlotTopology {
            id: id.into(),
            title: id.into(),
            responsibility: format!("{id} operation"),
            active_module: Some(module.into()),
            required: order <= 40,
            category: category.into(),
            order,
        });
        snapshot.modules.push(ModuleTopology {
            id: module.into(),
            slot: id.into(),
            active: true,
            source,
            ..Default::default()
        });
    }
    for i in 0..tools {
        snapshot.tools.push(ToolTopology {
            name: format!("normal-tool-{i}"),
            description: format!("description for tool {i}"),
            safety: if i % 2 == 0 { "read-only" } else { "writes" }.into(),
            source: if i % 4 < 2 { "module" } else { "configured" }.into(),
            enabled: i % 4 < 2,
            registered: i % 2 == 0,
            ..Default::default()
        });
    }
    snapshot.edges = vec![
        TopologyEdge {
            from: "slot:workflow".into(),
            to: "slot:model".into(),
            kind: "runtime".into(),
            label: Some("request".into()),
        },
        TopologyEdge {
            from: "slot:workflow".into(),
            to: "tools".into(),
            kind: "uses".into(),
            label: None,
        },
    ];
    snapshot
}

fn edge_cases() -> TopologySnapshot {
    let mut snapshot = typical(6);
    snapshot.profile = " профиль   | \x60デモ\x60  ".into();
    snapshot.cwd = "  /fixture/工😀\t ".into();
    snapshot.hooks = vec!["a\nb".into(), "\u{2003}".into(), "\x60 x | y\x60".into()];
    snapshot
        .slots
        .iter_mut()
        .find(|slot| slot.id == "workflow")
        .unwrap()
        .active_module = Some("missing".into());
    snapshot
        .slots
        .iter_mut()
        .find(|slot| slot.id == "context")
        .unwrap()
        .active_module = Some("-".into());
    snapshot
        .slots
        .iter_mut()
        .find(|slot| slot.id == "policy")
        .unwrap()
        .active_module = None;
    snapshot
        .slots
        .iter_mut()
        .find(|slot| slot.id == "model")
        .unwrap()
        .active_module = Some("unsupplied".into());
    for (slot, id) in [("workflow", "missing"), ("context", "-")] {
        snapshot.modules.insert(
            0,
            ModuleTopology {
                slot: slot.into(),
                id: id.into(),
                source: ModuleSourceTopology::Config,
                ..Default::default()
            },
        );
        snapshot.modules.push(ModuleTopology {
            slot: slot.into(),
            id: id.into(),
            source: ModuleSourceTopology::Unknown,
            ..Default::default()
        });
    }
    snapshot.slots.push(SlotTopology {
        id: "語😀\0".into(),
        active_module: Some(String::new()),
        order: 45,
        responsibility: " multiline\r\n cell | value ".into(),
        ..Default::default()
    });
    snapshot.tools[0].name = "e\u{301} 😀 語".into();
    snapshot.tools[1].name = "tool | \n\r\t\0".into();
    snapshot.tools[1].safety.clear();
    snapshot.tools[2].source.clear();
    snapshot
        .warnings
        .push(TopologyWarning::warn("line1\r\nline2 | 😀"));
    snapshot
}

fn variable_case(seed: usize) -> TopologySnapshot {
    let mut snapshot = if seed % 4 == 0 {
        edge_cases()
    } else {
        typical(seed % 21)
    };
    snapshot.module_epoch = seed as u64;
    snapshot.slots.rotate_left(seed % 8);
    snapshot.modules.reverse();
    if seed % 5 == 0 {
        snapshot.modules.retain(|module| module.slot != "model");
    }
    if seed % 7 == 0 {
        snapshot.slots.truncate(seed % 9);
    }
    if seed % 3 == 0 {
        snapshot.hooks.clear();
    }
    if seed % 17 == 0 {
        snapshot.model = None;
        snapshot.config_path = None;
    }
    snapshot
}

#[test]
fn exact_all_renderers() {
    let fixtures = [
        TopologySnapshot::default(),
        typical(16),
        edge_cases(),
        typical(64),
    ];
    let mut out = std::io::BufWriter::new(
        std::fs::File::create(std::env::var_os("R61_SNAPSHOT").unwrap()).unwrap(),
    );
    let mut count = 0;
    for (case, snapshot) in fixtures
        .into_iter()
        .chain((0..128).map(variable_case))
        .enumerate()
    {
        let unchanged = snapshot.clone();
        for (name, before, after) in RENDERERS {
            let expected = before(&snapshot);
            let actual = after(&snapshot);
            assert_eq!(
                actual.as_bytes(),
                expected.as_bytes(),
                "{name}, fixture {case}"
            );
            out.write_all(&(actual.len() as u64).to_le_bytes()).unwrap();
            out.write_all(actual.as_bytes()).unwrap();
            count += 1;
        }
        assert_eq!(snapshot, unchanged);
    }
    out.flush().unwrap();
    assert_eq!(count, 792);
    println!("{count} byte-identical renderer outputs across 132 fixtures");
}

#[test]
fn source_fallbacks_remain_distinct() {
    let snapshot = edge_cases();
    let table = candidate::render_topology_table(&snapshot);
    assert!(
        table
            .lines()
            .any(|line| line.starts_with("model ") && line.trim_end().ends_with(" -"))
    );
    assert!(
        table
            .lines()
            .any(|line| line.starts_with("context ") && line.trim_end().ends_with(" config"))
    );
    assert!(!table.lines().any(|line| line.starts_with("policy ")));
    let map = candidate::render_topology_map(&snapshot);
    let model = map
        .lines()
        .find(|line| line.contains("slot:model") && line.contains("active="))
        .unwrap();
    assert!(model.contains("source=unknown"));
    let path = candidate::render_topology_runtime_path(&snapshot);
    let context = path
        .lines()
        .find(|line| line.starts_with("  context"))
        .unwrap();
    assert!(context.contains("[- "));
    let runtime = candidate::render_topology_runtime_mermaid(&snapshot);
    assert!(runtime.contains("workflow<br/>missing<br/>-"));
    assert!(runtime.contains("context<br/>-<br/>config"));
}

#[test]
fn render_allocation_calls_and_requested_bytes() {
    for (case, snapshot) in [
        ("empty", TopologySnapshot::default()),
        ("ordinary-16", typical(16)),
        ("unicode-and-fallbacks", edge_cases()),
        ("stress-64", typical(64)),
    ] {
        for (name, before, after) in RENDERERS {
            let (stock_output, stock) =
                test_alloc::measure(|| black_box(before(black_box(&snapshot))));
            let (new_output, new) = test_alloc::measure(|| black_box(after(black_box(&snapshot))));
            assert_eq!(stock_output.as_bytes(), new_output.as_bytes());
            assert!(
                new.calls <= stock.calls && new.bytes <= stock.bytes,
                "{case} {name}"
            );
            if name == "full-mermaid" {
                assert_eq!((new.calls, new.bytes), (stock.calls, stock.bytes));
            } else if case == "ordinary-16" || case == "stress-64" {
                assert!(
                    new.calls < stock.calls && new.bytes < stock.bytes,
                    "{case} {name}"
                );
            }
            if name == "table" && case.starts_with("ordinary") {
                assert_eq!(stock.calls - new.calls, 8 * 3 + 16 * 5);
            }
            println!(
                "{case:22} {name:16} calls {:4} -> {:4}; requested bytes {:7} -> {:7}",
                stock.calls, new.calls, stock.bytes, new.bytes
            );
        }
    }
}
