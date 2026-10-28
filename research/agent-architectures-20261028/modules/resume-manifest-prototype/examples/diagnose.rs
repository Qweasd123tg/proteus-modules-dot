//! Synthetic caller declarations, not identities measured from Proteus binaries.
//! No file/network access, migration or resume. This example has not been run.
use resume_manifest::{
    compare, EngineIdentity, Evidence, ExportIdentity, ExportRef, Identity,
    Inventory, ModuleIdentity, ResumeManifest, Sha256Digest, StateSchema,
    TopologyIdentity, WorkflowIdentity, FORMAT_VERSION,
};

fn id(value: &str) -> Identity { Identity::new(value).expect("valid example identity") }
fn known(value: &str) -> Evidence<Identity> { Evidence::Known(id(value)) }
fn mock_digest(byte: u8) -> Evidence<Sha256Digest> {
    // Deliberately fake: never use these bytes to identify a real artifact.
    Evidence::Known(Sha256Digest::from_bytes([byte; 32]))
}
fn inventory<T>(entries: Vec<(&str, T)>) -> Evidence<Inventory<T>> {
    Evidence::Known(Inventory::try_new(entries.into_iter()
        .map(|(key, value)| (id(key), value)).collect()).expect("unique example IDs"))
}

fn main() {
    let saved = ResumeManifest {
        format_version: FORMAT_VERSION,
        // An illustrative label, not a claim about Proteus's current protocol.
        protocol_version: known("example-host-protocol-v1"),
        engine: EngineIdentity {
            contract_id: known("example-engine"),
            semantic_version: known("engine-behavior-2026-10-28"),
            artifact_digest: mock_digest(0x11),
        },
        workflow: WorkflowIdentity {
            contract_id: known("example-research-workflow"),
            semantic_version: known("behavior-1.0.0"),
            selected_export: Evidence::Known(ExportRef {
                module_id: id("research-module"), export_id: id("workflow.run"),
            }),
        },
        state_schema: StateSchema {
            id: known("example-research-state"), version: known("v1"),
            schema_digest: mock_digest(0x22),
        },
        modules: inventory(vec![("research-module", ModuleIdentity {
            artifact_digest: mock_digest(0x33),
            exports: inventory(vec![("workflow.run", ExportIdentity {
                contract_version: known("export-contract-v1"),
                schema_digest: mock_digest(0x44),
            })]),
        })]),
        topology: TopologyIdentity {
            encoding_version: known("example-graph-signature-v1"),
            topology_version: known("topology-1"),
            shape_digest: mock_digest(0x55),
            node_ids: inventory(vec![("collect", ()), ("summarize", ())]),
        },
        reducer_versions: inventory(vec![("messages.merge", known("ordered-v1"))]),
    };
    println!("Equal declarations, NOT execution permission: {:?}", compare(&saved, &saved));

    let mut changed = saved.clone();
    changed.workflow.semantic_version = known("behavior-1.0.1");
    println!("Patch label is NOT assumed compatible: {:?}", compare(&saved, &changed));

    let mut incomplete = saved.clone();
    incomplete.engine.artifact_digest = Evidence::Unknown;
    println!("Unknown compared with itself is NOT Exact: {:?}",
        compare(&incomplete, &incomplete));
}
