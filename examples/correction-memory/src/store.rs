//! Every method uses a fresh SQLite connection. No handle crosses a host callback.
use crate::{
    config::*,
    evidence::{Observation, validate_observation},
    types::*,
    util::{canonical, sha256},
};
use anyhow::{Context, Result, ensure};
use rusqlite::{
    Connection, DatabaseName, OpenFlags, OptionalExtension, TransactionBehavior, params,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::BTreeMap,
    fs::{self, OpenOptions},
    io::Read,
    os::unix::fs::{MetadataExt, OpenOptionsExt},
    path::{Path, PathBuf},
    time::Duration,
};

const APP_ID: u32 = 0x50434153;
const META: &str = "CREATE TABLE store_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL CHECK(schema_version=1), store_id TEXT NOT NULL, instance_id TEXT NOT NULL, workspace_cwd TEXT NOT NULL, database_path TEXT NOT NULL, policy_sha256 TEXT NOT NULL)";
const OPS: &str = "CREATE TABLE operations (operation_id TEXT PRIMARY KEY, request BLOB NOT NULL, request_sha256 TEXT NOT NULL, outcome TEXT NOT NULL, observation TEXT NOT NULL) WITHOUT ROWID";
const ENTRIES: &str = "CREATE TABLE entries (key TEXT PRIMARY KEY, revision INTEGER NOT NULL CHECK(revision>=1), last_operation TEXT NOT NULL REFERENCES operations(operation_id) DEFERRABLE INITIALLY DEFERRED) WITHOUT ROWID";

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Record {
    pub request: ApplyRequest,
    pub outcome: Outcome,
    pub observation: Observation,
}
#[derive(Debug, Clone, Serialize)]
pub struct Entry {
    pub identity: Identity,
    pub key: String,
    pub revision: u64,
    pub record: Option<Record>,
}
#[derive(Debug, Clone, Serialize)]
pub struct OperationRead {
    pub identity: Identity,
    pub operation_id: String,
    pub record: Option<Record>,
}
struct EncodedRecord {
    request: Vec<u8>,
    digest: String,
    outcome: String,
    observation: String,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stage {
    BeforeMutation,
    AfterEntry,
    BeforeCommit,
    AfterCommit,
    BeforeReturn,
}

pub struct Store<'a> {
    config: &'a Config,
    policy_hash: &'a str,
    cwd: String,
    path: PathBuf,
}
impl<'a> Store<'a> {
    pub fn resolve(config: &'a Config, policy_hash: &'a str, cwd: &Path) -> Result<Self> {
        config.validate()?;
        ensure!(cfg!(target_os = "linux"), "unsupported_platform");
        let cwd_text = cwd.to_str().ok_or_else(|| anyhow::anyhow!("cwd_utf8"))?;
        ensure!(
            cwd.is_absolute() && cwd_text.len() <= 4096 && !cwd_text.chars().any(char::is_control),
            "cwd_invalid"
        );
        let actual = fs::canonicalize(cwd).context("cwd_unavailable")?;
        ensure!(actual.as_os_str() == cwd.as_os_str(), "cwd_not_canonical");
        // Only the operator-configured relative path is traversed. No parent creation.
        let mut parent = cwd.to_path_buf();
        let components: Vec<_> = config.database_path.split('/').collect();
        for component in &components[..components.len() - 1] {
            parent.push(component);
            let metadata = fs::symlink_metadata(&parent).context("store_parent_unavailable")?;
            ensure!(
                metadata.is_dir() && !metadata.file_type().is_symlink(),
                "store_parent_type"
            );
        }
        let metadata = fs::symlink_metadata(&parent)?;
        // geteuid has no side effects and returns the current process identity.
        let uid = unsafe { libc::geteuid() };
        ensure!(
            metadata.uid() == uid && metadata.mode() & 0o077 == 0,
            "store_parent_not_private"
        );
        Ok(Self {
            config,
            policy_hash,
            cwd: cwd_text.into(),
            path: cwd.join(&config.database_path),
        })
    }
    pub fn path(&self) -> &Path {
        &self.path
    }
    fn preflight(&self) -> Result<()> {
        let mut file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)
            .map_err(|e| {
                if e.kind() == std::io::ErrorKind::NotFound {
                    anyhow::anyhow!("not_initialized")
                } else {
                    anyhow::anyhow!("store_open_error")
                }
            })?;
        let m = file.metadata()?;
        ensure!(m.is_file() && m.nlink() == 1, "store_file_type");
        ensure!(
            m.uid() == unsafe { libc::geteuid() } && m.mode() & 0o077 == 0,
            "store_file_not_private"
        );
        ensure!(
            (4096..=MAX_DATABASE).contains(&m.len()) && m.len() % 4096 == 0,
            "invalid_store_size"
        );
        let mut h = [0u8; 100];
        file.read_exact(&mut h).context("invalid_store_header")?;
        ensure!(
            &h[..16] == b"SQLite format 3\0" && u16::from_be_bytes([h[16], h[17]]) == 4096,
            "invalid_store_header"
        );
        ensure!(h[18] == 1 && h[19] == 1, "store_requires_rollback_format");
        ensure!(
            u32::from_be_bytes(h[60..64].try_into().unwrap()) == 1
                && u32::from_be_bytes(h[68..72].try_into().unwrap()) == APP_ID,
            "invalid_store_marker"
        );
        Ok(())
    }
    fn open(&self, write: bool) -> Result<Connection> {
        self.preflight()?;
        let flags = if write {
            OpenFlags::SQLITE_OPEN_READ_WRITE
        } else {
            OpenFlags::SQLITE_OPEN_READ_ONLY
        };
        let conn = Connection::open_with_flags(
            &self.path,
            flags
                | OpenFlags::SQLITE_OPEN_NO_MUTEX
                | OpenFlags::SQLITE_OPEN_PRIVATE_CACHE
                | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )
        .map_err(sql_error)?;
        ensure!(
            conn.is_readonly(DatabaseName::Main).map_err(sql_error)? != write,
            "store_read_only"
        );
        configure(&conn, write)?;
        Ok(conn)
    }
    fn identity(&self, conn: &Connection, expected: Option<&Identity>) -> Result<Identity> {
        let mut stmt = conn
            .prepare(
                "SELECT CASE WHEN length(CAST(name AS BLOB))<=64 THEN name ELSE NULL END,
                 CASE WHEN length(CAST(sql AS BLOB))<=8192 THEN sql ELSE NULL END
                 FROM sqlite_schema LIMIT 4",
            )
            .map_err(sql_error)?;
        let rows: Vec<(String, String)> = stmt
            .query_map([], |r| Ok((r.get(0)?, r.get(1)?)))
            .map_err(sql_error)?
            .collect::<rusqlite::Result<_>>()
            .map_err(sql_error)?;
        // Tables and triggers can share a name. Do not let map collection hide
        // a fourth object by replacing another row with the same key.
        ensure!(rows.len() == 3, "invalid_store_schema");
        let got: BTreeMap<String, String> = rows.into_iter().collect();
        let wanted: BTreeMap<_, _> = [
            ("store_meta".to_owned(), META.to_owned()),
            ("operations".to_owned(), OPS.to_owned()),
            ("entries".to_owned(), ENTRIES.to_owned()),
        ]
        .into();
        ensure!(got == wanted, "invalid_store_schema");
        let count: i64 = conn
            .query_row("SELECT count(*) FROM store_meta", [], |r| r.get(0))
            .map_err(sql_error)?;
        ensure!(count == 1, "invalid_store_identity");
        let identity = conn
            .query_row(
                "SELECT schema_version,
             CASE WHEN length(CAST(store_id AS BLOB))<=64 THEN store_id ELSE NULL END,
             CASE WHEN length(CAST(instance_id AS BLOB))=32 THEN instance_id ELSE NULL END,
             CASE WHEN length(CAST(workspace_cwd AS BLOB))<=4096 THEN workspace_cwd ELSE NULL END,
             CASE WHEN length(CAST(database_path AS BLOB))<=512 THEN database_path ELSE NULL END,
             CASE WHEN length(CAST(policy_sha256 AS BLOB))=64 THEN policy_sha256 ELSE NULL END
             FROM store_meta WHERE singleton=1",
                [],
                |r| {
                    Ok(Identity {
                        schema_version: r.get(0)?,
                        store_id: r.get(1)?,
                        database_instance_id: r.get(2)?,
                        workspace_cwd: r.get(3)?,
                        database_path: r.get(4)?,
                        policy_sha256: r.get(5)?,
                    })
                },
            )
            .map_err(sql_error)?;
        ensure!(
            identity.schema_version == 1 && identity.store_id == self.config.store_id,
            "store_identity_mismatch"
        );
        ensure!(
            identity.workspace_cwd == self.cwd
                && identity.database_path == self.config.database_path,
            "store_location_mismatch"
        );
        ensure!(
            identity.policy_sha256 == self.policy_hash,
            "store_policy_mismatch"
        );
        ensure!(
            identity.database_instance_id.len() == 32
                && identity
                    .database_instance_id
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            "invalid_store_instance"
        );
        if let Some(expected) = expected {
            ensure!(
                identity.database_instance_id == expected.database_instance_id,
                "store_instance_mismatch"
            );
            ensure!(&identity == expected, "proposal_identity_mismatch");
        }
        let mode: String = conn
            .query_row("PRAGMA journal_mode", [], |r| r.get(0))
            .map_err(sql_error)?;
        ensure!(mode == "delete", "store_journal_mode");
        Ok(identity)
    }
    pub fn init<T>(
        &self,
        mut poll: impl FnMut(Stage) -> Result<()>,
        build: impl Fn(&Identity) -> Result<T>,
    ) -> Result<T> {
        poll(Stage::BeforeMutation)?;
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)
        {
            Ok(file) => drop(file),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                let conn = self.open(false)?;
                let identity = self.identity(&conn, None)?;
                let response = build(&identity)?;
                poll(Stage::BeforeReturn)?;
                return Ok(response);
            }
            Err(_) => anyhow::bail!("store_create_error"),
        }
        // No CREATE flag: the exclusively-created empty file is the sole target.
        // Failure leaves an explicit incomplete-init artifact, never auto-repaired.
        let mut conn = Connection::open_with_flags(
            &self.path,
            OpenFlags::SQLITE_OPEN_READ_WRITE
                | OpenFlags::SQLITE_OPEN_NO_MUTEX
                | OpenFlags::SQLITE_OPEN_PRIVATE_CACHE
                | OpenFlags::SQLITE_OPEN_NOFOLLOW,
        )
        .map_err(sql_error)?;
        ensure!(
            !conn.is_readonly(DatabaseName::Main).map_err(sql_error)?,
            "store_read_only"
        );
        configure(&conn, true)?;
        conn.execute_batch(
            "PRAGMA page_size=4096; PRAGMA journal_mode=DELETE; PRAGMA max_page_count=4096;",
        )
        .map_err(sql_error)?;
        let tx = conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(sql_error)?;
        for sql in [META, OPS, ENTRIES] {
            tx.execute_batch(sql).map_err(sql_error)?;
        }
        tx.pragma_update(None, "application_id", APP_ID)
            .map_err(sql_error)?;
        tx.pragma_update(None, "user_version", 1)
            .map_err(sql_error)?;
        let instance: String = tx
            .query_row("SELECT lower(hex(randomblob(16)))", [], |r| r.get(0))
            .map_err(sql_error)?;
        let identity = Identity {
            schema_version: 1,
            store_id: self.config.store_id.clone(),
            database_instance_id: instance,
            workspace_cwd: self.cwd.clone(),
            database_path: self.config.database_path.clone(),
            policy_sha256: self.policy_hash.into(),
        };
        canonical(&identity, 8192)?;
        let response = build(&identity)?;
        tx.execute(
            "INSERT INTO store_meta VALUES(1,1,?1,?2,?3,?4,?5)",
            params![
                identity.store_id,
                identity.database_instance_id,
                identity.workspace_cwd,
                identity.database_path,
                identity.policy_sha256
            ],
        )
        .map_err(sql_error)?;
        poll(Stage::BeforeCommit)?;
        tx.commit().map_err(|_| anyhow::anyhow!("commit_unknown"))?;
        poll(Stage::AfterCommit)?;
        Ok(response)
    }
    pub fn read_entry(&self, key: &str) -> Result<Entry> {
        ensure!(id(key, 128), "invalid_key");
        let mut conn = self.open(false)?;
        let tx = conn.transaction().map_err(sql_error)?;
        let identity = self.identity(&tx, None)?;
        let state: Option<(u64, Option<String>)> = tx
            .query_row(
                "SELECT revision, CASE WHEN length(CAST(last_operation AS BLOB))<=64
                 THEN last_operation ELSE NULL END FROM entries WHERE key=?1",
                [key],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()
            .map_err(sql_error)?;
        let (revision, record) = match state {
            None => (0, None),
            Some((revision, op)) => {
                let op = op
                    .filter(|value| id(value, 64))
                    .ok_or_else(|| anyhow::anyhow!("invalid_store_entry_operation"))?;
                let record = self
                    .record(&tx, &identity, &op)?
                    .ok_or_else(|| anyhow::anyhow!("invalid_store_entry"))?;
                ensure!(
                    record.outcome.decision == Decision::Applied
                        && record.outcome.key == key
                        && record.outcome.resulting_revision == Some(revision),
                    "invalid_store_entry"
                );
                (revision, Some(record))
            }
        };
        Ok(Entry {
            identity,
            key: key.into(),
            revision,
            record,
        })
    }
    pub fn read_operation(&self, op: &str) -> Result<OperationRead> {
        ensure!(id(op, 64), "invalid_operation_id");
        let mut conn = self.open(false)?;
        let tx = conn.transaction().map_err(sql_error)?;
        let identity = self.identity(&tx, None)?;
        let record = self.record(&tx, &identity, op)?;
        Ok(OperationRead {
            identity,
            operation_id: op.into(),
            record,
        })
    }
    /// Freshness check + durable replay lookup; all connection state drops on return.
    pub fn before_verify(&self, request: &ApplyRequest) -> Result<Option<Record>> {
        request.validate(self.config)?;
        let mut conn = self.open(false)?;
        let tx = conn.transaction().map_err(sql_error)?;
        let identity = self.identity(&tx, None)?;
        if let Some(record) = self.record(&tx, &identity, &request.operation_id)? {
            same_request(&record, request)?;
            return Ok(Some(record));
        }
        self.identity(&tx, Some(&request.proposal.identity()))?;
        Ok(None)
    }
    fn record(&self, conn: &Connection, identity: &Identity, op: &str) -> Result<Option<Record>> {
        // SQL length predicates prevent fetching oversized corrupt cells into Rust.
        let row = conn
            .query_row(
                "SELECT CASE WHEN length(request)<=32896 THEN request ELSE NULL END,
             CASE WHEN length(CAST(request_sha256 AS BLOB))=64 THEN request_sha256 ELSE NULL END,
             CASE WHEN length(CAST(outcome AS BLOB))<=4096 THEN outcome ELSE NULL END,
             CASE WHEN length(CAST(observation AS BLOB))<=32768 THEN observation ELSE NULL END
             FROM operations WHERE operation_id=?1",
                [op],
                |r| {
                    Ok(EncodedRecord {
                        request: r.get(0)?,
                        digest: r.get(1)?,
                        outcome: r.get(2)?,
                        observation: r.get(3)?,
                    })
                },
            )
            .optional()
            .map_err(sql_error)?;
        let Some(EncodedRecord {
            request: bytes,
            digest,
            outcome,
            observation,
        }) = row
        else {
            return Ok(None);
        };
        ensure!(
            hash(&digest) && sha256(&bytes) == digest,
            "invalid_store_request_digest"
        );
        let request: ApplyRequest =
            serde_json::from_slice(&bytes).context("invalid_store_request")?;
        request.validate(self.config)?;
        ensure!(
            canonical(&request, MAX_PROPOSAL + 128)? == bytes
                && request.operation_id == op
                && request.proposal.identity() == *identity,
            "invalid_store_request_identity"
        );
        let outcome: Outcome = serde_json::from_str(&outcome).context("invalid_store_outcome")?;
        let observation: Observation =
            serde_json::from_str(&observation).context("invalid_store_observation")?;
        validate_observation(
            self.config,
            Path::new(&self.cwd),
            &request.proposal.evidence,
            &observation.verifier_call_id,
            &observation,
        )?;
        ensure!(
            outcome == make_outcome(&request, &observation, outcome.observed_revision)?,
            "invalid_store_outcome"
        );
        Ok(Some(Record {
            request,
            outcome,
            observation,
        }))
    }
    /// Prebuild the outward response before any SQL mutation. Fault stages are
    /// ordinary callback polls in production, deterministic seams in authored tests.
    pub fn apply<T>(
        &self,
        request: &ApplyRequest,
        observation: &Observation,
        mut poll: impl FnMut(Stage) -> Result<()>,
        build: impl Fn(&Record, bool) -> Result<T>,
    ) -> Result<T> {
        request.validate(self.config)?;
        poll(Stage::BeforeMutation)?;
        // A newly replaced database may carry a hot rollback journal. Refuse it
        // through a read-only open before any read-write connection can recover
        // it. This is additional to, not a substitute for, write-tx validation.
        {
            let mut read = self.open(false)?;
            let tx = read.transaction().map_err(sql_error)?;
            self.identity(&tx, Some(&request.proposal.identity()))?;
        }
        let mut conn = self.open(true)?;
        let tx = conn
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(sql_error)?;
        // Mandatory on the actual write connection AFTER the host callback.
        let identity = self.identity(&tx, Some(&request.proposal.identity()))?;
        if let Some(record) = self.record(&tx, &identity, &request.operation_id)? {
            same_request(&record, request)?;
            let response = build(&record, true)?;
            poll(Stage::BeforeReturn)?;
            return Ok(response);
        }
        validate_observation(
            self.config,
            Path::new(&self.cwd),
            &request.proposal.evidence,
            &observation.verifier_call_id,
            observation,
        )?;
        let operation_count: i64 = tx
            .query_row("SELECT count(*) FROM operations", [], |r| r.get(0))
            .map_err(sql_error)?;
        ensure!(
            operation_count < MAX_OPERATIONS as i64,
            "operation_capacity"
        );
        let revision: u64 = tx
            .query_row(
                "SELECT revision FROM entries WHERE key=?1",
                [&request.proposal.key],
                |r| r.get(0),
            )
            .optional()
            .map_err(sql_error)?
            .unwrap_or(0);
        let outcome = make_outcome(request, observation, revision)?;
        if outcome.decision == Decision::Applied && revision == 0 {
            let keys: i64 = tx
                .query_row("SELECT count(*) FROM entries", [], |r| r.get(0))
                .map_err(sql_error)?;
            ensure!(keys < MAX_KEYS as i64, "key_capacity");
        }
        let request_bytes = canonical(request, MAX_PROPOSAL + 128)?;
        let outcome_bytes = canonical(&outcome, 4096)?;
        let observation_bytes = canonical(observation, MAX_OBSERVATION)?;
        let record = Record {
            request: request.clone(),
            outcome,
            observation: observation.clone(),
        };
        let response = build(&record, false)?;
        // Identity is validated before this database-size guard is installed.
        tx.pragma_update(None, "max_page_count", 4096)
            .map_err(sql_error)?;
        poll(Stage::BeforeMutation)?;
        if let Some(next) = record.outcome.resulting_revision {
            let rows = if revision == 0 {
                tx.execute(
                    "INSERT INTO entries(key,revision,last_operation) VALUES(?1,?2,?3)",
                    params![request.proposal.key, next, request.operation_id],
                )
                .map_err(sql_error)?
            } else {
                tx.execute(
                    "UPDATE entries SET revision=?1,last_operation=?2 WHERE key=?3 AND revision=?4",
                    params![next, request.operation_id, request.proposal.key, revision],
                )
                .map_err(sql_error)?
            };
            ensure!(rows == 1, "conditional_write_failed");
        }
        poll(Stage::AfterEntry)?;
        tx.execute("INSERT INTO operations(operation_id,request,request_sha256,outcome,observation) VALUES(?1,?2,?3,?4,?5)",params![request.operation_id,request_bytes,record.outcome.request_sha256,std::str::from_utf8(&outcome_bytes)?,std::str::from_utf8(&observation_bytes)?]).map_err(sql_error)?;
        poll(Stage::BeforeCommit)?;
        tx.commit().map_err(|_| anyhow::anyhow!("commit_unknown"))?;
        poll(Stage::AfterCommit)?;
        Ok(response)
    }
}
fn configure(conn: &Connection, write: bool) -> Result<()> {
    conn.busy_timeout(Duration::from_millis(100))
        .map_err(sql_error)?;
    conn.execute_batch("PRAGMA trusted_schema=OFF; PRAGMA foreign_keys=ON; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-1024;").map_err(sql_error)?;
    if write {
        conn.execute_batch("PRAGMA synchronous=FULL;")
            .map_err(sql_error)?;
    }
    Ok(())
}
fn same_request(record: &Record, request: &ApplyRequest) -> Result<()> {
    let incoming = canonical(request, MAX_PROPOSAL + 128)?;
    ensure!(
        sha256(&incoming) == record.outcome.request_sha256
            && incoming == canonical(&record.request, MAX_PROPOSAL + 128)?,
        "operation_payload_mismatch"
    );
    Ok(())
}
fn make_outcome(
    request: &ApplyRequest,
    observation: &Observation,
    revision: u64,
) -> Result<Outcome> {
    ensure!(revision <= MAX_REVISION, "invalid_store_revision");
    let p = &request.proposal;
    let applied = revision == p.expected_revision;
    ensure!(!applied || revision < MAX_REVISION, "revision_exhausted");
    Ok(Outcome {
        schema_version: 1,
        store_id: p.store_id.clone(),
        database_instance_id: p.database_instance_id.clone(),
        workspace_cwd: p.workspace_cwd.clone(),
        database_path: p.database_path.clone(),
        operation_id: request.operation_id.clone(),
        request_sha256: sha256(&canonical(request, MAX_PROPOSAL + 128)?),
        key: p.key.clone(),
        expected_revision: p.expected_revision,
        observed_revision: revision,
        decision: if applied {
            Decision::Applied
        } else {
            Decision::Conflict
        },
        resulting_revision: if applied { Some(revision + 1) } else { None },
        proposal_sha256: sha256(&canonical(p, MAX_PROPOSAL)?),
        evidence_observation_sha256: sha256(&canonical(observation, MAX_OBSERVATION)?),
    })
}
fn sql_error(error: rusqlite::Error) -> anyhow::Error {
    match &error {
        rusqlite::Error::SqliteFailure(code, _)
            if matches!(
                code.code,
                rusqlite::ErrorCode::DatabaseBusy | rusqlite::ErrorCode::DatabaseLocked
            ) =>
        {
            anyhow::anyhow!("busy")
        }
        rusqlite::Error::SqliteFailure(code, _) if code.code == rusqlite::ErrorCode::DiskFull => {
            anyhow::anyhow!("capacity")
        }
        _ => anyhow::anyhow!("storage_error"),
    }
}
