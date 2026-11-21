use super::*;
use crate::{core::ProviderProfileConfig, domain::ModelRef, r60_alloc::measure};
use serde_json::json;

fn profile(provider: &str, model: &str) -> ProviderProfileConfig {
    let mut row = ProviderProfileConfig::default();
    row.provider = provider.into();
    row.model = model.into();
    row.reasoning.effort = Some("high".into());
    row
}

fn config(active: Option<&str>, rows: &[(&str, &str, &str)]) -> AppConfig {
    let mut c = AppConfig::default();
    c.active_provider = active.map(str::to_owned);
    c.providers = rows
        .iter()
        .map(|(alias, provider, model)| (alias.to_string(), profile(provider, model)))
        .collect();
    c
}

#[test]
fn r60_configured_model_options_are_exact_with_owned_fields() {
    let p = [
        ("a", "local", "m1"),
        ("b", "local", "m1"),
        ("c", "remote", "m2"),
        ("z", "local", "模型🌍"),
    ];
    let mut large = config(Some("z"), &p);
    large.providers.extend((0..124).map(|i| {
        (
            format!("p-{i:03}"),
            profile("synthetic", &format!("model-{i:03}")),
        )
    }));
    let mut over = config(Some("a"), &p);
    for value in over.providers.values_mut() {
        value.provider.reserve(4096);
        value.model.reserve(4096);
    }
    let mut output = vec![];
    for (label, c) in [
        ("no_profiles", config(None, &[])),
        ("missing_active_empty", config(Some("absent"), &[])),
        ("default_one", AppConfig::default()),
        ("four_aliases", config(Some("z"), &p)),
        ("no_active", config(None, &p)),
        ("blank_alias", config(Some(" "), &p)),
        ("missing_active", config(Some("absent"), &p)),
        (
            "empty_names",
            config(Some("b"), &[("a", "", ""), ("b", "local", "")]),
        ),
        ("excess_capacity_source", over),
        ("many_profiles_stress", large),
    ] {
        let input_snapshot = serde_json::to_vec(&c).unwrap();
        let (stock, a) = measure(|| stock_configured_model_options(&c));
        let (candidate, b) = measure(|| configured_model_options(&c));
        let new_wire = serde_json::to_vec(&candidate).unwrap();
        assert_eq!(
            new_wire,
            serde_json::to_vec(&stock).unwrap(),
            "{label}: wire parity"
        );
        assert_eq!(
            serde_json::to_vec(&c).unwrap(),
            input_snapshot,
            "{label}: config changed"
        );
        let conversions: Vec<_> = c
            .active_model_config()
            .ok()
            .into_iter()
            .chain(
                c.providers
                    .values()
                    .filter_map(|p| p.to_model_config().ok()),
            )
            .collect();
        let fields = conversions.iter().flat_map(|m| [&m.provider, &m.model]);
        let saved_calls = fields.clone().filter(|s| !s.is_empty()).count();
        let saved_bytes = fields.map(String::len).sum::<usize>();
        assert_eq!(a.calls - b.calls, saved_calls, "{label}: allocation calls");
        assert_eq!(a.bytes - b.bytes, saved_bytes, "{label}: requested bytes");
        for (left, right) in stock.iter().zip(&candidate) {
            assert_eq!(left.provider.capacity(), right.provider.capacity());
            assert_eq!(left.model.capacity(), right.model.capacity());
        }
        if label == "four_aliases" {
            assert_eq!(
                candidate,
                [
                    ModelRef::new("local", "模型🌍"),
                    ModelRef::new("local", "m1"),
                    ModelRef::new("remote", "m2"),
                ]
            );
        }
        println!(
            "r60 {label}: calls {}->{}, bytes {}->{}, models {}",
            a.calls,
            b.calls,
            a.bytes,
            b.bytes,
            candidate.len()
        );
        output.push(json!([label, candidate]));
    }

    let model = ["", "X", "模型", "X\0", "x / y", "a\r\n"];
    for left in model {
        for right in model {
            for active in [None, Some("a"), Some("z"), Some("missing")] {
                let c = config(active, &[("a", "p", left), ("z", "p", right)]);
                let candidate = configured_model_options(&c);
                assert_eq!(
                    serde_json::to_vec(&candidate).unwrap(),
                    serde_json::to_vec(&stock_configured_model_options(&c)).unwrap()
                );
                output.push(json!(candidate));
            }
        }
    }
    assert_eq!(output.len(), 154);
    let path = std::env::var("R60_OPTION_SNAPSHOT").unwrap();
    std::fs::write(path, serde_json::to_vec(&output).unwrap()).unwrap();
}
