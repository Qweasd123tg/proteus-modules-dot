//! Opt-in, unwired host-facing compatibility diagnostics. No storage or execution.
//!
//! `Exact` means only that the complete identities declared by the caller match.
//! This crate does not attest artifacts, grant authority, migrate state, or resume.
#![forbid(unsafe_code)]

use sha2::{Digest as _, Sha256};
use std::collections::BTreeMap;
use std::fmt;

pub const FORMAT_VERSION: u32 = 1;
pub const MAX_IDENTITY_BYTES: usize = 1024;
pub const MAX_INVENTORY_ENTRIES: usize = 4096;
pub const MAX_CANONICAL_BYTES: usize = 1024 * 1024;
pub const MAX_DIAGNOSTIC_BLOCKERS: usize = 256;

/// Opaque, case-sensitive UTF-8 identity; no SemVer or Unicode normalization.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct Identity(String);

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum IdentityError { Empty, TooLong, WhitespaceOrControl }

impl Identity {
    pub fn new(value: impl Into<String>) -> Result<Self, IdentityError> {
        let value = value.into();
        if value.is_empty() { return Err(IdentityError::Empty); }
        if value.len() > MAX_IDENTITY_BYTES { return Err(IdentityError::TooLong); }
        if value.trim() != value || value.chars().any(char::is_control) {
            return Err(IdentityError::WhitespaceOrControl);
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str { &self.0 }
}

/// Missing means not recorded; Unknown means explicitly not established.
/// Neither is equivalent to a known value, even when both sides are identical.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Evidence<T> { Missing, Unknown, Known(T) }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Sha256Digest([u8; 32]);

impl Sha256Digest {
    /// Caller-supplied identity, not proof that the corresponding bytes exist.
    pub const fn from_bytes(bytes: [u8; 32]) -> Self { Self(bytes) }
    pub const fn as_bytes(&self) -> &[u8; 32] { &self.0 }
}

impl fmt::Display for Sha256Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for byte in self.0 { write!(f, "{byte:02x}")?; }
        Ok(())
    }
}

/// Ordered immutable map. Construction rejects duplicate IDs, never last-wins.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Inventory<T>(BTreeMap<Identity, T>);

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InventoryError { TooManyEntries, DuplicateId(Identity) }

impl<T> Inventory<T> {
    pub fn try_new(entries: Vec<(Identity, T)>) -> Result<Self, InventoryError> {
        if entries.len() > MAX_INVENTORY_ENTRIES {
            return Err(InventoryError::TooManyEntries);
        }
        let mut map = BTreeMap::new();
        for (id, value) in entries {
            if map.contains_key(&id) { return Err(InventoryError::DuplicateId(id)); }
            map.insert(id, value);
        }
        Ok(Self(map))
    }

    pub fn get(&self, id: &Identity) -> Option<&T> { self.0.get(id) }
    pub fn iter(&self) -> impl Iterator<Item = (&Identity, &T)> { self.0.iter() }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExportRef { pub module_id: Identity, pub export_id: Identity }

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EngineIdentity {
    pub contract_id: Evidence<Identity>,
    pub semantic_version: Evidence<Identity>,
    pub artifact_digest: Evidence<Sha256Digest>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkflowIdentity {
    pub contract_id: Evidence<Identity>,
    pub semantic_version: Evidence<Identity>,
    pub selected_export: Evidence<ExportRef>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StateSchema {
    pub id: Evidence<Identity>,
    pub version: Evidence<Identity>,
    pub schema_digest: Evidence<Sha256Digest>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExportIdentity {
    pub contract_version: Evidence<Identity>,
    /// Host-canonicalized complete export/tool input-output contract identity.
    pub schema_digest: Evidence<Sha256Digest>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ModuleIdentity {
    pub artifact_digest: Evidence<Sha256Digest>,
    pub exports: Evidence<Inventory<ExportIdentity>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TopologyIdentity {
    /// Declares rules for the externally supplied graph signature, not its code.
    pub encoding_version: Evidence<Identity>,
    pub topology_version: Evidence<Identity>,
    pub shape_digest: Evidence<Sha256Digest>,
    /// Unit values make a duplicate-rejecting, sorted set of node identities.
    pub node_ids: Evidence<Inventory<()>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ResumeManifest {
    pub format_version: u32,
    pub protocol_version: Evidence<Identity>,
    pub engine: EngineIdentity,
    pub workflow: WorkflowIdentity,
    pub state_schema: StateSchema,
    pub modules: Evidence<Inventory<ModuleIdentity>>,
    pub topology: TopologyIdentity,
    pub reducer_versions: Evidence<Inventory<Evidence<Identity>>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CanonicalError { UnsupportedFormat(u32), ByteLimitExceeded }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Side { Saved, Candidate }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Unavailable { Missing, Unknown }

/// Field order is also the stable order of reported differences.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Dimension {
    Protocol, EngineContract, EngineSemantics, EngineArtifact,
    WorkflowContract, WorkflowSemantics, WorkflowExport,
    StateSchema, Modules, Topology, Reducers,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Blocker {
    Unencodable { side: Side, error: CanonicalError },
    Unavailable { side: Side, path: String, state: Unavailable },
    UnlistedWorkflowExport { side: Side, selected: ExportRef },
    UnsupportedChange(Dimension),
    /// At most MAX_DIAGNOSTIC_BLOCKERS detailed blockers precede this marker.
    DiagnosticsTruncated,
}

#[derive(Clone, Debug, PartialEq, Eq)]
#[must_use = "A diagnostic is not permission to resume or migrate"]
pub enum Decision {
    Exact { manifest_digest: Sha256Digest },
    /// There are known differences. No claim that a migration exists or is safe.
    ExplicitMigrationRequired {
        saved_digest: Sha256Digest,
        candidate_digest: Sha256Digest,
        changes: Vec<Dimension>,
    },
    Incompatible { blockers: Vec<Blocker>, changes: Vec<Dimension> },
}

impl ResumeManifest {
    /// Diagnostic identity, including distinct tags for Missing and Unknown.
    /// A digest can be computed for incomplete data; it does not imply Exact.
    pub fn canonical_digest(&self) -> Result<Sha256Digest, CanonicalError> {
        Ok(hash(&self.canonical_bytes()?))
    }

    /// Versioned, length-delimited representation; not a checkpoint payload.
    pub fn canonical_bytes(&self) -> Result<Vec<u8>, CanonicalError> {
        if self.format_version != FORMAT_VERSION {
            return Err(CanonicalError::UnsupportedFormat(self.format_version));
        }
        let mut out = Encoder(Vec::new());
        out.raw(b"proteus.resume-manifest\0")?;
        out.raw(&self.format_version.to_be_bytes())?;
        self.protocol_version.encode(&mut out)?;
        self.engine.encode(&mut out)?;
        self.workflow.encode(&mut out)?;
        self.state_schema.encode(&mut out)?;
        self.modules.encode(&mut out)?;
        self.topology.encode(&mut out)?;
        self.reducer_versions.encode(&mut out)?;
        Ok(out.0)
    }
}

/// Pure comparison over caller declarations. No I/O, grants, migrations or resume.
pub fn compare(saved: &ResumeManifest, candidate: &ResumeManifest) -> Decision {
    let mut blockers = Vec::new();
    let encoded = (saved.canonical_bytes(), candidate.canonical_bytes());
    let (saved_bytes, candidate_bytes) = match encoded {
        (Ok(a), Ok(b)) => (a, b),
        (a, b) => {
            if let Err(error) = a {
                blockers.push(Blocker::Unencodable { side: Side::Saved, error });
            }
            if let Err(error) = b {
                blockers.push(Blocker::Unencodable { side: Side::Candidate, error });
            }
            return Decision::Incompatible { blockers, changes: Vec::new() };
        }
    };
    inspect(saved, Side::Saved, &mut blockers);
    inspect(candidate, Side::Candidate, &mut blockers);
    let changes = differences(saved, candidate);
    for dimension in &changes {
        if matches!(dimension, Dimension::Protocol | Dimension::EngineContract
            | Dimension::WorkflowContract) {
            push_blocker(&mut blockers, Blocker::UnsupportedChange(*dimension));
        }
    }
    if !blockers.is_empty() { return Decision::Incompatible { blockers, changes }; }
    // Compare canonical bytes, not only hashes. Hashes are reporting identities.
    if saved_bytes == candidate_bytes {
        Decision::Exact { manifest_digest: hash(&saved_bytes) }
    } else {
        Decision::ExplicitMigrationRequired {
            saved_digest: hash(&saved_bytes),
            candidate_digest: hash(&candidate_bytes),
            changes,
        }
    }
}

fn differences(a: &ResumeManifest, b: &ResumeManifest) -> Vec<Dimension> {
    let mut out = Vec::new();
    macro_rules! changed {
        ($field:ident, $a:expr, $b:expr) => {
            if $a != $b { out.push(Dimension::$field); }
        };
    }
    changed!(Protocol, a.protocol_version, b.protocol_version);
    changed!(EngineContract, a.engine.contract_id, b.engine.contract_id);
    changed!(EngineSemantics, a.engine.semantic_version, b.engine.semantic_version);
    changed!(EngineArtifact, a.engine.artifact_digest, b.engine.artifact_digest);
    changed!(WorkflowContract, a.workflow.contract_id, b.workflow.contract_id);
    changed!(WorkflowSemantics, a.workflow.semantic_version, b.workflow.semantic_version);
    changed!(WorkflowExport, a.workflow.selected_export, b.workflow.selected_export);
    changed!(StateSchema, a.state_schema, b.state_schema);
    changed!(Modules, a.modules, b.modules);
    changed!(Topology, a.topology, b.topology);
    changed!(Reducers, a.reducer_versions, b.reducer_versions);
    out
}

fn require<'a, T>(value: &'a Evidence<T>, side: Side, path: &str,
    blockers: &mut Vec<Blocker>) -> Option<&'a T> {
    let state = match value {
        Evidence::Known(value) => return Some(value),
        Evidence::Missing => Unavailable::Missing,
        Evidence::Unknown => Unavailable::Unknown,
    };
    push_blocker(blockers, Blocker::Unavailable { side, path: path.to_owned(), state });
    None
}

fn inspect(m: &ResumeManifest, side: Side, blockers: &mut Vec<Blocker>) {
    macro_rules! required {
        ($value:expr, $path:expr) => { require($value, side, $path, blockers) };
    }
    let _ = required!(&m.protocol_version, "protocol_version");
    let _ = required!(&m.engine.contract_id, "engine.contract_id");
    let _ = required!(&m.engine.semantic_version, "engine.semantic_version");
    let _ = required!(&m.engine.artifact_digest, "engine.artifact_digest");
    let _ = required!(&m.workflow.contract_id, "workflow.contract_id");
    let _ = required!(&m.workflow.semantic_version, "workflow.semantic_version");
    let selected = required!(&m.workflow.selected_export, "workflow.selected_export");
    let _ = required!(&m.state_schema.id, "state_schema.id");
    let _ = required!(&m.state_schema.version, "state_schema.version");
    let _ = required!(&m.state_schema.schema_digest, "state_schema.schema_digest");
    let modules = required!(&m.modules, "modules");
    if let Some(modules) = modules {
        for (id, module) in modules.iter() {
            let path = format!("modules[{:?}]", id.as_str());
            let _ = required!(&module.artifact_digest, &format!("{path}.artifact_digest"));
            if let Some(exports) = required!(&module.exports, &format!("{path}.exports")) {
                for (id, export) in exports.iter() {
                    let path = format!("{path}.exports[{:?}]", id.as_str());
                    let _ = required!(&export.contract_version, &format!("{path}.contract_version"));
                    let _ = required!(&export.schema_digest, &format!("{path}.schema_digest"));
                }
            }
        }
        if let Some(selected) = selected {
            let unlisted = match modules.get(&selected.module_id) {
                None => true,
                Some(module) => match &module.exports {
                    Evidence::Known(exports) => exports.get(&selected.export_id).is_none(),
                    _ => false, // Already diagnosed as missing/unknown, not unlisted.
                },
            };
            if unlisted {
                push_blocker(blockers, Blocker::UnlistedWorkflowExport {
                    side, selected: selected.clone(),
                });
            }
        }
    }
    let _ = required!(&m.topology.encoding_version, "topology.encoding_version");
    let _ = required!(&m.topology.topology_version, "topology.topology_version");
    let _ = required!(&m.topology.shape_digest, "topology.shape_digest");
    let _ = required!(&m.topology.node_ids, "topology.node_ids");
    if let Some(reducers) = required!(&m.reducer_versions, "reducer_versions") {
        for (id, version) in reducers.iter() {
            let _ = required!(version, &format!("reducer_versions[{:?}]", id.as_str()));
        }
    }
}

fn hash(bytes: &[u8]) -> Sha256Digest {
    Sha256Digest(Sha256::digest(bytes).into())
}

fn push_blocker(blockers: &mut Vec<Blocker>, blocker: Blocker) {
    if blockers.len() < MAX_DIAGNOSTIC_BLOCKERS {
        blockers.push(blocker);
    } else if blockers.len() == MAX_DIAGNOSTIC_BLOCKERS {
        blockers.push(Blocker::DiagnosticsTruncated);
    }
}

struct Encoder(Vec<u8>);

impl Encoder {
    fn raw(&mut self, bytes: &[u8]) -> Result<(), CanonicalError> {
        if bytes.len() > MAX_CANONICAL_BYTES.saturating_sub(self.0.len()) {
            return Err(CanonicalError::ByteLimitExceeded);
        }
        self.0.extend_from_slice(bytes);
        Ok(())
    }
    fn count(&mut self, value: usize) -> Result<(), CanonicalError> {
        let value = u32::try_from(value).map_err(|_| CanonicalError::ByteLimitExceeded)?;
        self.raw(&value.to_be_bytes())
    }
}

trait Encode { fn encode(&self, out: &mut Encoder) -> Result<(), CanonicalError>; }

impl Encode for Identity {
    fn encode(&self, out: &mut Encoder) -> Result<(), CanonicalError> {
        out.count(self.0.len())?;
        out.raw(self.0.as_bytes())
    }
}
impl Encode for Sha256Digest {
    fn encode(&self, out: &mut Encoder) -> Result<(), CanonicalError> { out.raw(&self.0) }
}
impl Encode for () {
    fn encode(&self, _: &mut Encoder) -> Result<(), CanonicalError> { Ok(()) }
}
impl<T: Encode> Encode for Evidence<T> {
    fn encode(&self, out: &mut Encoder) -> Result<(), CanonicalError> {
        match self {
            Self::Missing => out.raw(&[0]),
            Self::Unknown => out.raw(&[1]),
            Self::Known(value) => { out.raw(&[2])?; value.encode(out) }
        }
    }
}
impl<T: Encode> Encode for Inventory<T> {
    fn encode(&self, out: &mut Encoder) -> Result<(), CanonicalError> {
        out.count(self.0.len())?;
        for (id, value) in &self.0 { id.encode(out)?; value.encode(out)?; }
        Ok(())
    }
}

// Canonical v1 field order. Changing these lists requires a new format version.
macro_rules! encode_fields {
    ($ty:ty, $($field:ident),+ $(,)?) => {
        impl Encode for $ty {
            fn encode(&self, out: &mut Encoder) -> Result<(), CanonicalError> {
                $(self.$field.encode(out)?;)+
                Ok(())
            }
        }
    };
}
encode_fields!(ExportRef, module_id, export_id);
encode_fields!(EngineIdentity, contract_id, semantic_version, artifact_digest);
encode_fields!(WorkflowIdentity, contract_id, semantic_version, selected_export);
encode_fields!(StateSchema, id, version, schema_digest);
encode_fields!(ExportIdentity, contract_version, schema_digest);
encode_fields!(ModuleIdentity, artifact_digest, exports);
encode_fields!(TopologyIdentity, encoding_version, topology_version, shape_digest, node_ids);
