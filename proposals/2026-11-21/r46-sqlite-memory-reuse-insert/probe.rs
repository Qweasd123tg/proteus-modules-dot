use super::*;
use proteus_contracts::{
    contracts::{ExecutionAttribution, ProcessContextProviderInput, ProcessContextProviderRequest},
    domain::{AgentTask, ToolCall, new_execution_id},
    process_module::{
        ContextProviderModule, ToolModule, ToolModuleHost, ToolModuleInvocationContext,
    },
};
use serde_json::json;
use std::{env, hint::black_box, time::Instant};

struct Host;
impl ToolModuleHost for Host {
    fn is_cancelled(&self) -> Result<bool, ProcessModuleError> {
        Ok(false)
    }
}

#[test]
fn time_real_surfaces() {
    let case = env::var("R46_CASE").unwrap();
    let iterations = 2000;
    let store = Arc::new(SqliteMemoryStore { conn: fresh_conn() });
    let ctx = ToolModuleInvocationContext {
        cwd: ".".into(),
        attribution: ExecutionAttribution::detached(new_execution_id()),
        skills: Default::default(),
        config: json!({}),
    };
    let ctx = serde_json::to_string(&ctx).unwrap();
    let write = tools::MemoryTool {
        store: store.clone(),
        remember: true,
    };
    let recall = tools::MemoryTool {
        store: store.clone(),
        remember: false,
    };
    let provider = provider::MemoryProvider {
        store: store.clone(),
    };
    let call =
        |name: &str, args: Value| serde_json::to_string(&ToolCall::new("r46", name, args)).unwrap();
    let write_call = |i: usize| {
        call(
            "remember_fact",
            json!({
                "kind": if i % 2 == 0 {"fact"} else {"preference"},
                "content": format!("indexed species sample{i}"),
                "metadata": {"i":i, "labels":["ёж","alpha"],"flag":null},
            }),
        )
    };
    for i in 0..96 {
        write
            .invoke_json(write_call(i), ctx.clone(), &mut Host)
            .unwrap();
    }
    let calls = (0..iterations)
        .map(|i| match case.as_str() {
            "remember" => write_call(i + 96),
            "recent" => call("recall_memory", json!({"query":"", "limit":1+(i%2)})),
            "fts_tool" => call(
                "recall_memory",
                json!({
                    "query": format!("sample{}", i%96), "limit":1+(i%2)
                }),
            ),
            "fts_provider" => serde_json::to_string(&ProcessContextProviderRequest {
                input: ProcessContextProviderInput {
                    provider_id: "sqlite_memory".into(),
                    task: AgentTask::new("look up a sample", ".".into()),
                    metadata: json!({"text":format!("sample{}", i%96), "limit":1+(i%2)}),
                },
                attribution: ExecutionAttribution::detached(new_execution_id()),
                skills: Default::default(),
            })
            .unwrap(),
            _ => panic!("unexpected case"),
        })
        .collect::<Vec<_>>();
    let mut bodies = Vec::with_capacity(iterations);
    let start = Instant::now();
    for input in calls {
        let output = match case.as_str() {
            "remember" => write.invoke_json(input, ctx.clone(), &mut Host),
            "fts_provider" => provider.provide_json(input),
            _ => recall.invoke_json(input, ctx.clone(), &mut Host),
        }
        .unwrap();
        bodies.push(black_box(output));
    }
    let elapsed = start.elapsed().as_nanos();
    if case == "remember" {
        for query in [
            json!({"query":"sample2095","limit":1}),
            json!({"query":"","limit":3}),
        ] {
            bodies.push(
                recall
                    .invoke_json(call("recall_memory", query), ctx.clone(), &mut Host)
                    .unwrap(),
            );
        }
        assert_eq!(
            store
                .conn
                .lock()
                .unwrap()
                .query_row("SELECT count(*) FROM memory_items", [], |row| row
                    .get::<_, i64>(0))
                .unwrap(),
            (iterations + 96) as i64
        );
    }
    std::fs::write(env::var_os("R46_OUTPUT").unwrap(), bodies.join("\n")).unwrap();
    println!("R46 {elapsed} {iterations}");
}
