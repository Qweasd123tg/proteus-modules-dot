mod candidate;
mod stock;
mod test_alloc;

pub use proteus_contracts::contracts;

use anyhow::{Result, bail};
use contracts::{
    PROCESS_MODEL_DESCRIBE_METHOD, ProcessModelDescribeRequest, ProcessModelDescriptor,
};
use proteus_contracts::{
    domain::{
        HostedToolConfig, HostedToolKind, ModelRef, ToolSafety, ToolSpec, ToolSurface,
        WebSearchHostedToolConfig,
    },
    model_standard::ModelCapabilities,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, hint::black_box, io::Write as _, sync::Mutex as StdMutex};

type DescriptorMap = BTreeMap<(String, String), ProcessModelDescriptor>;

struct FixtureClient {
    replies: DescriptorMap,
    actions: StdMutex<Vec<String>>,
}

impl FixtureClient {
    fn invoke_blocking(
        &self,
        method: &str,
        request: &ProcessModelDescribeRequest,
    ) -> Result<ProcessModelDescriptor> {
        assert_eq!(method, PROCESS_MODEL_DESCRIBE_METHOD);
        let model = &request.model;
        self.actions
            .lock()
            .unwrap()
            .push(format!("describe {}/{}", model.provider, model.model));
        let key = (model.provider.clone(), model.model.clone());
        match self.replies.get(&key) {
            Some(value) => Ok(value.clone()),
            None => bail!(
                "fixture transport: no descriptor for {}/{}",
                model.provider,
                model.model
            ),
        }
    }

    fn reset(&self) {
        self.actions.lock().unwrap().push("reset".into());
    }
}

fn descriptor(id: &str, mode: usize, long_schema: usize) -> ProcessModelDescriptor {
    let mut capabilities = ModelCapabilities::basic_text_and_tools()
        .with_streaming(mode % 2 == 0)
        .with_max_input_tokens(Some(128 + mode as u32));
    let hosted_tools = if mode % 3 == 0 {
        vec![]
    } else {
        capabilities = capabilities.with_provider_hosted_tools(vec![HostedToolKind::WebSearch]);
        vec![
            ToolSpec::new(
                "web_search",
                "Search information",
                json!({"type":"object","properties":{"q":{"type":"string","title":"я😀".repeat(long_schema)}}}),
                ToolSafety::Network,
            ).with_surface(ToolSurface::provider_hosted(HostedToolConfig::WebSearch {
                config: WebSearchHostedToolConfig::default(),
            })),
        ]
    };
    ProcessModelDescriptor {
        adapter_id: id.into(),
        capabilities,
        hosted_tools,
    }
}

fn key(provider: &str, model: &str) -> (String, String) {
    (provider.into(), model.into())
}

macro_rules! adapter {
    ($which:ident, $cache:expr, $replies:expr) => {
        $which::ProcessModel {
            client: FixtureClient {
                replies: $replies,
                actions: StdMutex::new(Vec::new()),
            },
            adapter_id: "fixture-model".into(),
            descriptions: StdMutex::new($cache),
        }
    };
}

fn outcome<T>(result: Result<T>, encode: impl FnOnce(T) -> Value) -> Value {
    match result {
        Ok(value) => json!({"ok":encode(value)}),
        Err(error) => json!({"error":format!("{error:#}")}),
    }
}

macro_rules! trace {
    ($model:ident, $queries:expr) => {{
        let mut observations = vec![];
        for (reference, hosted) in $queries {
            observations.push(if *hosted {
                outcome($model.provider_hosted_tools(reference), |value| {
                    json!(value)
                })
            } else {
                outcome($model.capabilities(reference), |value| json!(value))
            });
        }
        let cache = $model.descriptions.lock().unwrap();
        let cache_entries = cache
            .iter()
            .map(|(key, value)| json!([key, value]))
            .collect::<Vec<_>>();
        (
            observations,
            $model.client.actions.lock().unwrap().clone(),
            cache_entries,
        )
    }};
}

#[test]
fn byte_parity_for_hits_misses_failures_and_full_cached_state() {
    let file = std::fs::File::create(std::env::var_os("R65_SNAPSHOT").unwrap()).unwrap();
    let mut out = std::io::BufWriter::new(file);
    let mut cases = 0;
    for i in 0..96 {
        let cached = descriptor("fixture-model", i, i % 4);
        let cold = descriptor("fixture-model", i + 1, i % 8);
        let other_provider = descriptor("fixture-model", i + 2, 1);
        let wrong = descriptor("switched-id", 2, 1);
        let cache = DescriptorMap::from([(key("fixture", "cached"), cached)]);
        let incoming = DescriptorMap::from([
            (key("fixture", "cold"), cold),
            (key("different", "cold"), other_provider),
            (key("fixture", "wrong"), wrong),
        ]);
        let before = adapter!(stock, cache.clone(), incoming.clone());
        let after = adapter!(candidate, cache, incoming);
        let order = [
            (ModelRef::new("fixture", "cached"), false),
            (ModelRef::new("fixture", "cached"), true),
            (ModelRef::new("fixture", "cold"), i % 2 == 0),
            (ModelRef::new("fixture", "cold"), i % 2 != 0),
            (ModelRef::new("different", "cold"), true),
            (ModelRef::new("different", "cold"), false),
            (ModelRef::new("fixture", "wrong"), false),
            (ModelRef::new("fixture", "missing"), true),
            (ModelRef::new("fixture", "wrong"), true),
            (ModelRef::new("fixture", "cached"), false),
        ];
        let a = trace!(before, &order);
        let b = trace!(after, &order);
        assert_eq!(a, b);
        assert_eq!(
            b.0[6]["error"],
            "model describe changed adapter_id for the same export"
        );
        assert_eq!(
            b.0[7]["error"],
            "fixture transport: no descriptor for fixture/missing"
        );
        assert_eq!(
            b.1,
            [
                "describe fixture/cold",
                "describe different/cold",
                "describe fixture/wrong",
                "reset",
                "describe fixture/missing",
                "describe fixture/wrong",
                "reset",
            ]
        );
        assert_eq!(b.2.len(), 3);
        let encoded = serde_json::to_vec(&b).unwrap();
        out.write_all(&(encoded.len() as u64).to_le_bytes())
            .unwrap();
        out.write_all(&encoded).unwrap();
        cases += 1;
    }
    out.flush().unwrap();
    assert_eq!(cases, 96);
    println!("{cases} byte-identical outcome/cache traces, covering 960 getter calls");
}

#[test]
fn requested_fields_still_own_their_data() {
    let model = ModelRef::new("fixture", "cached");
    let entry = descriptor("fixture-model", 2, 2);
    let inner = adapter!(
        candidate,
        DescriptorMap::from([(key("fixture", "cached"), entry.clone())]),
        DescriptorMap::new()
    );
    let mut capabilities = inner.capabilities(&model).unwrap();
    capabilities.provider_hosted_tools.clear();
    let mut tools = inner.provider_hosted_tools(&model).unwrap();
    tools[0].input_schema = json!({});
    assert_eq!(inner.capabilities(&model).unwrap(), entry.capabilities);
    assert_eq!(
        inner.provider_hosted_tools(&model).unwrap(),
        entry.hosted_tools
    );
    assert!(inner.client.actions.lock().unwrap().is_empty());
}

#[test]
fn warm_getters_measure_only_selected_owned_fields() {
    let model = ModelRef::new("fixture", "cached");
    for (name, entry) in [
        ("text-only", descriptor("fixture-model", 0, 0)),
        ("one-hosted-tool", descriptor("fixture-model", 1, 2)),
        ("large-unused-schema", descriptor("fixture-model", 2, 8192)),
    ] {
        let cache = DescriptorMap::from([(key("fixture", "cached"), entry)]);
        let old = adapter!(stock, cache.clone(), DescriptorMap::new());
        let new = adapter!(candidate, cache, DescriptorMap::new());
        let (a, a_count) = test_alloc::measure(|| {
            black_box(black_box(&old).capabilities(black_box(&model)).unwrap())
        });
        let (b, b_count) = test_alloc::measure(|| {
            black_box(black_box(&new).capabilities(black_box(&model)).unwrap())
        });
        assert_eq!(a, b);
        assert!(a_count.calls > b_count.calls && a_count.bytes > b_count.bytes);
        println!(
            "{name:20} capabilities  requests {:2} -> {:2}, bytes {:6} -> {:6}",
            a_count.calls, b_count.calls, a_count.bytes, b_count.bytes
        );
        let (a, a_count) = test_alloc::measure(|| {
            black_box(
                black_box(&old)
                    .provider_hosted_tools(black_box(&model))
                    .unwrap(),
            )
        });
        let (b, b_count) = test_alloc::measure(|| {
            black_box(
                black_box(&new)
                    .provider_hosted_tools(black_box(&model))
                    .unwrap(),
            )
        });
        assert_eq!(a, b);
        assert!(a_count.calls > b_count.calls && a_count.bytes > b_count.bytes);
        assert!(old.client.actions.lock().unwrap().is_empty());
        assert!(new.client.actions.lock().unwrap().is_empty());
        println!(
            "{name:20} hosted-tools  requests {:2} -> {:2}, bytes {:6} -> {:6}",
            a_count.calls, b_count.calls, a_count.bytes, b_count.bytes
        );
    }
}
