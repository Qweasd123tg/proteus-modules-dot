//! Actual modules, authored callback routing and an owned-artifact reader.
//! This is NOT Core policy, approval, canonical journaling, or official read_file.
use anyhow::{Result, ensure};
use proteus_example_correction_memory::{types::ApplyRequest, util::sha256, *};
use proteus_example_evidence_spans::{
    EvidenceSpans,
    config::{Config as SpanConfig, Source},
};
use proteus_module_sdk::{
    contracts::{
        contracts::{ExecutionAttribution, ProcessToolInvokeInput},
        domain::{ToolCall, ToolResult, new_execution_id},
        process_module::{ProcessModuleError, ToolModuleHost},
    },
    tool::ToolModule,
};
use serde_json::{Value, json};
use std::{
    fs,
    os::unix::fs::PermissionsExt,
    path::{Path, PathBuf},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
};
pub const ARTIFACT: &str = "channel=draft\npublish=false\n";
#[derive(Clone, Copy, PartialEq, Eq)]
pub enum ReaderFault {
    None,
    WrongMethod,
    WrongCallId,
    CancelAfterRead,
}
pub struct Fixture {
    pub dir: tempfile::TempDir,
    pub module: CorrectionMemory,
    pub router: Router,
}
pub struct Router {
    pub cwd: PathBuf,
    pub config: SpanConfig,
    pub trace: Arc<Mutex<Vec<ToolCall>>>,
    pub canceled: Arc<AtomicBool>,
    pub fault: ReaderFault,
}
impl Fixture {
    pub fn new() -> Result<Self> {
        let dir = tempfile::tempdir()?;
        fs::create_dir(dir.path().join("store"))?;
        fs::set_permissions(dir.path().join("store"), fs::Permissions::from_mode(0o700))?;
        fs::create_dir(dir.path().join("evidence"))?;
        fs::write(dir.path().join("evidence/release.txt"), ARTIFACT)?;
        let config = SpanConfig {
            schema_version: 1,
            sources: vec![Source {
                id: "release".into(),
                path: "evidence/release.txt".into(),
            }],
        };
        let spans = EvidenceSpans::new(config.clone())?;
        let module = CorrectionMemory::new(serde_json::from_value(
            json!({"schema_version":1,"store_id":"release-proposals","database_path":"store/notes.sqlite","evidence_policy":{"verifier_tool":"evidence.verify_spans","expected_config_sha256":spans.config_sha256(),"sources":[{"source_id":"release","path":"evidence/release.txt"}]}}),
        )?)?;
        let router = Router {
            cwd: dir.path().into(),
            config,
            trace: Arc::new(Mutex::new(vec![])),
            canceled: Arc::new(AtomicBool::new(false)),
            fault: ReaderFault::None,
        };
        Ok(Self {
            dir,
            module,
            router,
        })
    }
    pub fn call(&mut self, name: &str, args: Value) -> Result<ToolResult> {
        self.module.invoke(
            input(self.dir.path(), ToolCall::new("fixture-outer", name, args)),
            &mut self.router,
        )
    }
    pub fn prepare(
        &mut self,
        text: &str,
        claim: &str,
        start: u64,
        quote: &str,
    ) -> Result<ApplyRequest> {
        let r=self.call(PREPARE,json!({"key":"release.status","new_text":text,"evidence":{"source_id":"release","expected_sha256":sha256(ARTIFACT.as_bytes()),"claims":[{"claim_id":claim,"start_byte":start,"end_byte":start+quote.len() as u64,"quote":quote}]}}))?;
        ensure!(r.ok, "prepare failed: {:?}", r.error);
        Ok(ApplyRequest {
            operation_id: format!("op-{claim}"),
            proposal: serde_json::from_value(r.metadata[RESULT_KEY]["result"]["proposal"].clone())?,
        })
    }
    pub fn apply(&mut self, request: &ApplyRequest) -> Result<ToolResult> {
        self.call(APPLY, serde_json::to_value(request)?)
    }
}
fn input(cwd: &Path, call: ToolCall) -> ProcessToolInvokeInput {
    ProcessToolInvokeInput {
        call,
        cwd: cwd.into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: Default::default(),
    }
}
impl ToolModuleHost for Router {
    fn is_cancelled(&self) -> std::result::Result<bool, ProcessModuleError> {
        Ok(self.canceled.load(Ordering::SeqCst))
    }
    fn execute_tool_json(&self, raw: String) -> std::result::Result<String, ProcessModuleError> {
        let run = || -> Result<String> {
            let call: ToolCall = serde_json::from_str(&raw)?;
            ensure!(
                call.name == "evidence.verify_spans",
                "fixture unsupported callback"
            );
            self.trace.lock().unwrap().push(call.clone());
            let verifier = EvidenceSpans::new(self.config.clone())?;
            let mut reader = Reader {
                cwd: self.cwd.clone(),
                trace: self.trace.clone(),
                canceled: self.canceled.clone(),
                fault: self.fault,
            };
            let result = verifier.invoke(input(&self.cwd, call), &mut reader)?;
            Ok(serde_json::to_string(&result)?)
        };
        run().map_err(|e| ProcessModuleError::new(e.to_string()))
    }
}
struct Reader {
    cwd: PathBuf,
    trace: Arc<Mutex<Vec<ToolCall>>>,
    canceled: Arc<AtomicBool>,
    fault: ReaderFault,
}
impl ToolModuleHost for Reader {
    fn is_cancelled(&self) -> std::result::Result<bool, ProcessModuleError> {
        Ok(self.canceled.load(Ordering::SeqCst))
    }
    fn execute_tool_json(&self, raw: String) -> std::result::Result<String, ProcessModuleError> {
        let run = || -> Result<String> {
            let call: ToolCall = serde_json::from_str(&raw)?;
            ensure!(
                call.name == "read_file" && call.args == json!({"path":"evidence/release.txt"}),
                "fixture reader exact allowlist"
            );
            self.trace.lock().unwrap().push(call.clone());
            let path = self.cwd.join("evidence/release.txt");
            ensure!(fs::metadata(&path)?.len() <= 65536, "fixture artifact size");
            let text = fs::read_to_string(&path)?;
            ensure!(text.len() <= 65536, "fixture artifact size");
            let mut result=ToolResult::ok(call.id.clone(),text.clone()).with_metadata(json!({"tool":"read_file","path":path,"total_lines":text.lines().count(),"returned_lines":text.lines().count(),"truncated":false}));
            match self.fault {
                ReaderFault::None => {}
                ReaderFault::WrongMethod => result.metadata["tool"] = json!("another_reader"),
                ReaderFault::WrongCallId => result.call_id = "wrong-reader-occurrence".into(),
                ReaderFault::CancelAfterRead => self.canceled.store(true, Ordering::SeqCst),
            };
            Ok(serde_json::to_string(&result)?)
        };
        run().map_err(|e| ProcessModuleError::new(e.to_string()))
    }
}
pub fn workflow() -> Result<Value> {
    let mut f = Fixture::new()?;
    let init = f.call(INIT, json!({}))?;
    ensure!(init.ok, "init failed");
    let a = f.prepare("Release remains draft.", "channel", 0, "channel=draft")?;
    let b = f.prepare(
        "Do not publish this release.",
        "publish",
        14,
        "publish=false",
    )?;
    let applied = f.apply(&a)?;
    let conflict = f.apply(&b)?;
    ensure!(
        applied.metadata[RESULT_KEY]["result"]["outcome"]["decision"] == "applied",
        "missing applied result"
    );
    ensure!(
        conflict.metadata[RESULT_KEY]["result"]["outcome"]["decision"] == "conflict",
        "missing conflict result"
    );
    let before = f.router.trace.lock().unwrap().len();
    let replay = f.apply(&a)?;
    ensure!(
        f.router.trace.lock().unwrap().len() == before,
        "replay called verifier"
    );
    ensure!(
        applied.metadata[RESULT_KEY]["result"] == replay.metadata[RESULT_KEY]["result"],
        "unstable replay"
    );
    let mut changed = a.clone();
    changed.proposal.new_text = "Different payload.".into();
    let rejected = f.apply(&changed)?;
    ensure!(
        !rejected.ok
            && rejected
                .error
                .as_deref()
                .unwrap_or("")
                .contains("operation_payload_mismatch"),
        "changed payload accepted"
    );
    let current = f.call(READ, json!({"kind":"entry","key":"release.status"}))?;
    ensure!(
        current.metadata[RESULT_KEY]["result"]["revision"] == 1,
        "incorrect revision"
    );
    let trace = f.router.trace.lock().unwrap().clone();
    Ok(
        json!({"fixture_kind":"actual_modules_authored_callbacks_owned_artifact","actual_core":false,"host_approval_exercised":false,"init":init,"applied":applied,"conflict":conflict,"replay":replay,"changed_payload_rejected":rejected,"current":current,"nested_calls":trace}),
    )
}
