#![allow(dead_code)]
//! Explicit synthetic verifier receipts; real SQLite in owned private temp dirs.
use proteus_example_correction_memory::{
    config::Config,
    evidence::{EVIDENCE_KEY, Observation},
    types::*,
    util::sha256,
    *,
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
pub const TEXT: &str = "channel=draft\npublish=false\n";
pub fn config() -> Config {
    serde_json::from_value(json!({"schema_version":1,"store_id":"corrections","database_path":"store/notes.sqlite","evidence_policy":{"verifier_tool":"evidence.verify_spans","expected_config_sha256":"a".repeat(64),"sources":[{"source_id":"release","path":"evidence/release.txt"}]}})).unwrap()
}
pub fn request() -> PrepareRequest {
    serde_json::from_value(json!({"key":"release.status","new_text":"Release remains a draft.","evidence":{"source_id":"release","expected_sha256":sha256(TEXT.as_bytes()),"claims":[{"claim_id":"channel","start_byte":0,"end_byte":13,"quote":"channel=draft"}]}})).unwrap()
}
pub struct Env {
    pub dir: tempfile::TempDir,
    pub config: Config,
    pub module: CorrectionMemory,
}
impl Env {
    pub fn new() -> Self {
        let dir = tempfile::tempdir().unwrap();
        fs::create_dir(dir.path().join("store")).unwrap();
        fs::set_permissions(dir.path().join("store"), fs::Permissions::from_mode(0o700)).unwrap();
        let config = config();
        let module = CorrectionMemory::new(config.clone()).unwrap();
        Self {
            dir,
            config,
            module,
        }
    }
    pub fn cwd(&self) -> &Path {
        self.dir.path()
    }
    pub fn db(&self) -> PathBuf {
        self.cwd().join(&self.config.database_path)
    }
    pub fn host(&self) -> Host {
        Host::new(self.cwd())
    }
    pub fn init(&self) {
        let r = self.call(INIT, json!({}), &mut self.host());
        assert!(r.ok, "{r:?}");
    }
    pub fn call(&self, name: &str, args: Value, host: &mut Host) -> ToolResult {
        invoke(&self.module, self.cwd(), name, args, host)
    }
    pub fn prepared(&self) -> ApplyRequest {
        let r = self.call(
            PREPARE,
            serde_json::to_value(request()).unwrap(),
            &mut self.host(),
        );
        assert!(r.ok, "{r:?}");
        ApplyRequest {
            operation_id: "op-one".into(),
            proposal: serde_json::from_value(r.metadata[RESULT_KEY]["result"]["proposal"].clone())
                .unwrap(),
        }
    }
    pub fn apply(&self, r: &ApplyRequest, host: &mut Host) -> ToolResult {
        self.call(APPLY, serde_json::to_value(r).unwrap(), host)
    }
    pub fn entry(&self) -> Value {
        let r = self.call(
            READ,
            json!({"kind":"entry","key":"release.status"}),
            &mut self.host(),
        );
        assert!(r.ok, "{r:?}");
        r.metadata[RESULT_KEY]["result"].clone()
    }
    pub fn operation(&self, id: &str) -> Value {
        let r = self.call(
            READ,
            json!({"kind":"operation","operation_id":id}),
            &mut self.host(),
        );
        assert!(r.ok, "{r:?}");
        r.metadata[RESULT_KEY]["result"].clone()
    }
}
pub fn invoke(
    module: &CorrectionMemory,
    cwd: &Path,
    name: &str,
    args: Value,
    host: &mut Host,
) -> ToolResult {
    module
        .invoke(
            ProcessToolInvokeInput {
                call: ToolCall::new("outer-call", name, args),
                cwd: cwd.into(),
                attribution: ExecutionAttribution::detached(new_execution_id()),
                skills: Default::default(),
            },
            host,
        )
        .unwrap()
}
type Mutation = Box<dyn Fn(&ToolCall, &mut ToolResult) + Send + Sync>;
pub struct Host {
    pub cwd: PathBuf,
    pub calls: Mutex<Vec<ToolCall>>,
    pub mutate: Mutation,
    pub canceled: Arc<AtomicBool>,
    pub after: Box<dyn Fn() + Send + Sync>,
    pub raw: Option<String>,
}
impl Host {
    pub fn new(cwd: &Path) -> Self {
        Self {
            cwd: cwd.into(),
            calls: Mutex::new(vec![]),
            mutate: Box::new(|_, _| {}),
            canceled: Arc::new(AtomicBool::new(false)),
            after: Box::new(|| {}),
            raw: None,
        }
    }
    pub fn count(&self) -> usize {
        self.calls.lock().unwrap().len()
    }
}
impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(self.canceled.load(Ordering::SeqCst))
    }
    fn execute_tool_json(&self, raw: String) -> Result<String, ProcessModuleError> {
        let call: ToolCall = serde_json::from_str(&raw).unwrap();
        assert_eq!(call.name, "evidence.verify_spans");
        let request: EvidenceRequest = serde_json::from_value(call.args.clone()).unwrap();
        self.calls.lock().unwrap().push(call.clone());
        let observation = observation(&self.cwd, &request, &call.id);
        let mut result = ToolResult::ok(call.id.clone(), "synthetic exact-byte witness")
            .with_metadata(json!({EVIDENCE_KEY:observation,"duration_ms":1}));
        (self.mutate)(&call, &mut result);
        (self.after)();
        if let Some(raw) = &self.raw {
            return Ok(raw.clone());
        }
        Ok(serde_json::to_string(&result).unwrap())
    }
}
pub fn observation(cwd: &Path, r: &EvidenceRequest, id: &str) -> Observation {
    serde_json::from_value(json!({"schema_version":1,"status":"exact_byte_match","scope":"observed_host_read_bytes","source_id":r.source_id,"configured_path":"evidence/release.txt","observed_path":cwd.join("evidence/release.txt"),"config_sha256":"a".repeat(64),"content_sha256":r.expected_sha256,"source_bytes":TEXT.len(),"verifier_call_id":id,"reader_call_id":"reader-id","verified_claims":r.claims.iter().map(|c|json!({"claim_id":c.claim_id,"start_byte":c.start_byte,"end_byte":c.end_byte,"quote_sha256":sha256(c.quote.as_bytes())})).collect::<Vec<_>>(),"origin_verified":false,"semantic_entailment":"not_evaluated"})).unwrap()
}
pub fn outcome(r: &ToolResult) -> Value {
    assert!(r.ok, "{r:?}");
    r.metadata[RESULT_KEY]["result"]["outcome"].clone()
}
pub fn fail(r: &ToolResult, code: &str) {
    assert!(!r.ok, "{r:?}");
    assert!(
        r.error.as_deref().unwrap_or("").contains(code),
        "expected {code}, {r:?}"
    );
    assert!(r.metadata.get(RESULT_KEY).is_none());
}
