use std::{
    borrow::Cow,
    future::Future,
    pin::pin,
    sync::atomic::AtomicUsize,
    task::{Context, Poll, Waker},
};

use super::*;
use crate::{
    contracts::{
        ApprovalRequest, ApprovalResponse, Model, ModelEventStream, Tool, ToolContext, ToolRegistry,
    },
    domain::{EventEnvelope, ToolCall, ToolResult, ToolSafety, new_session_id, new_thread_id},
    model_standard::ModelCapabilities,
};

include!("r57_stock.rs");

#[path = "r57_alloc.rs"]
mod counting_alloc;

#[derive(Default)]
struct ObservedApproval(AtomicUsize);

#[async_trait]
impl ApprovalTransport for ObservedApproval {
    fn can_request_approval(&self) -> bool {
        self.0.fetch_add(1, Ordering::Relaxed);
        false
    }

    async fn request_approval(&self, _: ApprovalRequest) -> Result<ApprovalResponse> {
        anyhow::bail!("no approval request in the synthetic workflow")
    }
}

struct ObservedTool {
    spec: ToolSpec,
    visibility_calls: Arc<AtomicUsize>,
}

#[async_trait]
impl Tool for ObservedTool {
    fn spec(&self) -> ToolSpec {
        self.spec.clone()
    }

    fn model_visible(&self) -> bool {
        self.visibility_calls.fetch_add(1, Ordering::Relaxed);
        true
    }

    async fn invoke(&self, _: &ToolCall, _: ToolContext) -> Result<ToolResult> {
        anyhow::bail!("no tool invocation in the synthetic workflow")
    }
}

#[derive(Default)]
struct Starts {
    fail_next: AtomicBool,
    yield_next: AtomicBool,
    events: std::sync::Mutex<Vec<EventEnvelope>>,
}

#[async_trait]
impl EventSink for Starts {
    async fn append(&self, envelope: EventEnvelope) -> Result<()> {
        if !matches!(envelope.event, Event::SessionStarted { .. }) {
            return Ok(());
        }
        if self.yield_next.swap(false, Ordering::Relaxed) {
            tokio::task::yield_now().await;
        }
        if self.fail_next.swap(false, Ordering::Relaxed) {
            anyhow::bail!("simulated durable event sink failure");
        }
        self.events.lock().unwrap().push(envelope);
        Ok(())
    }
}

struct Fixture {
    _root: tempfile::TempDir,
    _workspace: tempfile::TempDir,
    runtime: AgentRuntime,
    approval: Arc<ObservedApproval>,
    visibility: Arc<AtomicUsize>,
    events: Arc<Starts>,
}

fn synthetic_model() -> ModelRef {
    ModelRef::new("test", "r57-synthetic")
}

impl Fixture {
    async fn new(resume: bool, tools: usize) -> Self {
        let root = tempfile::tempdir().unwrap();
        let workspace = tempfile::tempdir().unwrap();
        let cfg = root.path().join("config.toml");
        let storage = crate::test_support::storage(workspace.path());
        let approval = Arc::new(ObservedApproval::default());
        let visibility = Arc::new(AtomicUsize::new(0));
        let events = Arc::new(Starts {
            events: std::sync::Mutex::new(Vec::with_capacity(2)),
            ..Default::default()
        });
        let mut builder = AgentRuntime::builder(AppConfig::default(), workspace.path().to_owned())
            .with_module_catalog(test_catalog())
            .with_config_path(Some(&cfg))
            .with_session_storage(storage.clone())
            .with_event_sink(events.clone())
            .with_approval(approval.clone());
        if resume {
            let store = SessionStore::new(storage, root.path(), workspace.path(), new_session_id())
                .unwrap();
            store
                .append_history(
                    new_thread_id(),
                    None,
                    &[CanonicalMessage::text(MessageRole::User, "r57 synthetic")],
                )
                .await
                .unwrap();
            let revision = store.history_revision().await.unwrap();
            store.hibernate_writer().await;
            builder = builder.resume_from_session_view(store, revision, 1, new_thread_id());
        }
        let runtime = builder.build().unwrap();
        {
            let mut state = runtime.services.execution_state.write().await;
            assert!(state.runtime.config_snapshot.is_some());
            let mut registry = ToolRegistry::new();
            for i in 0..tools {
                let spec = ToolSpec::new(
                    format!("r57_probe_{i}"),
                    "catalog-only test tool",
                    serde_json::json!({
                        "type": "object",
                        "properties": { "value": {"type":"string", "description": "x".repeat(1024)} }
                    }),
                    ToolSafety::ReadOnly,
                );
                registry
                    .register(ObservedTool {
                        spec,
                        visibility_calls: visibility.clone(),
                    })
                    .unwrap();
            }
            state.runtime.registry.tools = registry;
            let mut snapshot = state.runtime.config_snapshot.take().unwrap();
            snapshot.tools = crate::core::SessionConfigTool::capture(&state.runtime.registry.tools);
            state.runtime.config_snapshot = Some(snapshot);
            state.model_ref = Some(synthetic_model());
        }
        approval.0.store(0, Ordering::Relaxed);
        visibility.store(0, Ordering::Relaxed);
        assert_eq!(*runtime.session.session_started.lock().await, resume);
        Self {
            _root: root,
            _workspace: workspace,
            runtime,
            approval,
            visibility,
            events,
        }
    }

    fn expected_event(&self, seq: u64) {
        let events = self.events.events.lock().unwrap();
        assert_eq!(events.len(), 1);
        let env = &events[0];
        assert_eq!(env.seq, seq);
        assert_eq!(env.session_id, self.runtime.session_id());
        assert_eq!(env.thread_id, self.runtime.session.thread_id);
        assert_eq!(env.turn_id, None);
        let Event::SessionStarted {
            session_id,
            cwd,
            model,
            session_dir,
        } = &env.event
        else {
            panic!("wrong lifecycle event");
        };
        assert_eq!(*session_id, env.session_id);
        assert_eq!(cwd, &self.runtime.services.cwd);
        assert_eq!(model, &Some(synthetic_model()));
        assert_eq!(session_dir.as_deref(), self.runtime.session_dir());
    }
}

fn measure_poll(f: impl Future<Output = Result<()>>) -> counting_alloc::Allocations {
    let mut future = pin!(f);
    let mut context = Context::from_waker(Waker::noop());
    let (result, count) = counting_alloc::measure(|| future.as_mut().poll(&mut context));
    let Poll::Ready(result) = result else {
        panic!("uncontended lifecycle sample yielded")
    };
    result.unwrap();
    count
}

#[tokio::test(flavor = "current_thread")]
async fn r57_lifecycle_scope_and_resume_work() {
    for resume in [false, true] {
        for tools in [0, 32] {
            let stock = Fixture::new(resume, tools).await;
            let candidate = Fixture::new(resume, tools).await;
            let capture_bytes = |f: &Fixture| {
                resume.then(|| {
                    let store = f.runtime.session_store().unwrap();
                    let journal = store.journal_path();
                    let bytes = std::fs::read(&journal).unwrap();
                    (journal, bytes)
                })
            };
            let canonicals = [capture_bytes(&stock), capture_bytes(&candidate)];
            for cycle in 0..3 {
                let (old, new);
                if cycle % 2 == 0 {
                    old = measure_poll(stock.runtime.r57_stock_start_session());
                    new = measure_poll(candidate.runtime.start_session());
                } else {
                    new = measure_poll(candidate.runtime.start_session());
                    old = measure_poll(stock.runtime.r57_stock_start_session());
                }
                assert_eq!(stock.approval.0.swap(0, Ordering::Relaxed), 1);
                assert_eq!(stock.visibility.swap(0, Ordering::Relaxed), tools);
                assert_eq!(candidate.approval.0.swap(0, Ordering::Relaxed), 0);
                assert_eq!(candidate.visibility.swap(0, Ordering::Relaxed), 0);
                assert!(
                    new.calls < old.calls && new.bytes < old.bytes,
                    "{old:?} -> {new:?}"
                );
                println!(
                    "resume={resume} tools={tools:2} cycle={cycle} alloc_calls={}→{} alloc_bytes={}→{} tool_visibility={tools}→0 approval_observations=1→0",
                    old.calls, new.calls, old.bytes, new.bytes
                );
            }
            for f in [&stock, &candidate] {
                assert!(*f.runtime.session.session_started.lock().await);
                if resume {
                    assert_eq!(f.events.events.lock().unwrap().len(), 0);
                } else {
                    f.expected_event(1);
                }
            }
            for (path, bytes) in canonicals.into_iter().flatten() {
                assert_eq!(std::fs::read(path).unwrap(), bytes);
            }
        }
    }
}

#[tokio::test(flavor = "current_thread")]
async fn r57_lifecycle_failure_retry_and_concurrent_start() {
    let stock = Fixture::new(false, 4).await;
    let candidate = Fixture::new(false, 4).await;
    for f in [&stock, &candidate] {
        f.events.fail_next.store(true, Ordering::Relaxed);
    }
    let (a, b) = tokio::join!(
        stock.runtime.r57_stock_start_session(),
        candidate.runtime.start_session()
    );
    for (fixture, result) in [(&stock, a), (&candidate, b)] {
        assert_eq!(
            result.unwrap_err().to_string(),
            "simulated durable event sink failure"
        );
        assert!(!*fixture.runtime.session.session_started.lock().await);
        fixture.events.yield_next.store(true, Ordering::Relaxed);
    }

    let (a, b, c) = tokio::join!(
        stock.runtime.r57_stock_start_session(),
        stock.runtime.r57_stock_start_session(),
        stock.runtime.r57_stock_start_session(),
    );
    a.unwrap();
    b.unwrap();
    c.unwrap();
    let (a, b, c) = tokio::join!(
        candidate.runtime.start_session(),
        candidate.runtime.start_session(),
        candidate.runtime.start_session(),
    );
    a.unwrap();
    b.unwrap();
    c.unwrap();
    stock.expected_event(2);
    candidate.expected_event(2);
}

struct NoInference;

#[async_trait]
impl Model for NoInference {
    fn id(&self) -> Cow<'static, str> {
        "r57-no-inference".into()
    }

    fn capabilities(&self, _: &ModelRef) -> Result<ModelCapabilities> {
        Ok(ModelCapabilities::basic_text_and_tools())
    }

    async fn stream(&self, _: CanonicalModelRequest) -> Result<ModelEventStream> {
        panic!("this workflow does not start inference")
    }
}

struct SyntheticWorkflow;
#[async_trait]
impl Workflow for SyntheticWorkflow {
    async fn run(
        &self,
        task: AgentTask,
        history: Vec<CanonicalMessage>,
        _: crate::contracts::WorkflowInvocationContext,
    ) -> Result<WorkflowOutput> {
        Ok(successful_messages(history, task, "r57 synthetic done"))
    }
}

#[tokio::test(flavor = "current_thread")]
async fn r57_lifecycle_real_turn_keeps_admission_capture() {
    let fixture = Fixture::new(false, 4).await;
    replace_workflow_for_test(&fixture.runtime, Arc::new(SyntheticWorkflow)).await;
    fixture
        .runtime
        .services
        .execution_state
        .write()
        .await
        .runtime
        .registry
        .replace_model_for_test(Arc::new(NoInference));
    let output = fixture.runtime.run("synthetic turn".into()).await.unwrap();
    assert_eq!(output, AgentOutput::text("done"));
    fixture.expected_event(1);
    assert!(
        fixture.approval.0.load(Ordering::Relaxed) > 0,
        "real turn still captures approval"
    );
    assert!(
        fixture.visibility.load(Ordering::Relaxed) >= 4,
        "real turn still captures tool metadata"
    );
}
