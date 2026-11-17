// Standalone data-only fixture. The production markdown.rs is included verbatim.
// The two adjacent sub-renderers are placeholders, not upstream implementations.
mod core {
    #[derive(Default)]
    pub struct TopologySnapshot {
        pub profile: String,
        pub cwd: String,
        pub module_epoch: usize,
        pub permission_mode: String,
        pub model: Option<Model>,
        pub config_path: Option<String>,
        pub hooks: Vec<String>,
        pub slots: Vec<Slot>,
        pub modules: Vec<Module>,
        pub tools: Vec<Tool>,
        pub warnings: Vec<Warning>,
    }
    pub struct Model { pub provider: String, pub name: String }
    pub struct Slot { pub id: String, pub active_module: Option<String>, pub responsibility: String }
    pub struct Module { pub slot: String, pub id: String, pub source: String }
    pub struct Tool { pub name: String, pub safety: String, pub source: String, pub enabled: bool, pub registered: bool, pub description: String }
    pub struct Warning { pub severity: String, pub message: String }
}
mod topology_render {
    mod helpers {
        pub(super) fn module_source_label(label: &str) -> String { label.into() }
        pub(super) fn yes_no(value: bool) -> &'static str { if value { "yes" } else { "no" } }
    }
    mod map { pub(super) fn render_topology_map(_: &crate::core::TopologySnapshot) -> String { "fixed-map".into() } }
    mod runtime { pub(super) fn render_topology_runtime_path(_: &crate::core::TopologySnapshot) -> String { "fixed-path".into() } }
    pub mod markdown { include!(env!("PINNED_MARKDOWN_RS")); }
}
fn main() {
    for value in std::env::args().skip(1) {
        let snap = core::TopologySnapshot {
            profile: "default".into(), cwd: value.clone(), permission_mode: "normal".into(),
            config_path: Some(value.clone()), hooks: vec!["one".into(), "two".into()],
            model: Some(core::Model { provider: "example".into(), name: value }),
            ..Default::default()
        };
        print!("{}\0", topology_render::markdown::render_topology_markdown(&snap));
    }
}

#[test]
fn topology_report_keeps_path_with_a_literal_backtick_in_one_code_span() {
    let snap = core::TopologySnapshot {
        cwd: "/tmp/a`b".into(),
        ..Default::default()
    };
    let report = topology_render::markdown::render_topology_markdown(&snap);
    // CommonMark allows padded or unpadded long fences for an interior backtick.
    let line = report.lines().find(|line| line.starts_with("cwd: ")).unwrap();
    assert!(matches!(line, "cwd: ``/tmp/a`b``" | "cwd: `` /tmp/a`b ``"), "{line}");
}
