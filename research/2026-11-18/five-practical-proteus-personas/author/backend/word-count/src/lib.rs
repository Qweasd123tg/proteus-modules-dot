//! The entire application-specific core. No filesystem, clock, randomness or host calls.
use anyhow::{Result, anyhow, ensure};
use proteus_module_sdk::contracts::domain::{ToolResult, ToolSafety, ToolSpec};
use serde_json::{Value, json};

pub fn specification() -> ToolSpec {
    ToolSpec::new(
        "count_words",
        "Count whitespace-separated words in the supplied text.",
        json!({
            "type": "object",
            "properties": {"text": {"type":"string"}},
            "required": ["text"],
            "additionalProperties": false
        }),
        ToolSafety::ReadOnly,
    )
}

pub fn response(call_id: String, args: &Value) -> Result<ToolResult> {
    let object = args
        .as_object()
        .ok_or_else(|| anyhow!("arguments must be an object"))?;
    ensure!(
        object.len() == 1 && object.contains_key("text"),
        "expected exactly one field: text"
    );
    let text = object["text"]
        .as_str()
        .ok_or_else(|| anyhow!("text must be a string"))?;
    Ok(ToolResult::ok(
        call_id,
        text.split_whitespace().count().to_string(),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn declares_one_required_string() {
        let spec = serde_json::to_value(specification()).unwrap();
        assert_eq!(spec["name"], "count_words");
        assert_eq!(
            spec["input_schema"],
            json!({
                "type":"object", "properties":{"text":{"type":"string"}},
                "required":["text"], "additionalProperties":false
            })
        );
    }

    #[test]
    fn real_result_keeps_each_call_id_and_uses_the_public_text_output() {
        for (i, (text, n)) in [
            ("", 0),
            ("   \t\r\n", 0),
            ("Proteus", 1),
            ("two  words\nthree", 3),
            ("Привет,\u{00a0}мир!", 2),
            ("кошка\u{3000}кот", 2),
            ("co-op", 1),
            ("東京", 1),
        ]
        .iter()
        .enumerate()
        {
            let id = format!("synthetic-{i}");
            let args = json!({"text":*text});
            let got = response(id.clone(), &args).unwrap();
            let expected = json!({"call_id":id,"ok":true,"output":n.to_string(),
                "content":[],"error":null,"metadata":null});
            assert_eq!(serde_json::to_value(&got).unwrap(), expected);
            let restored: ToolResult = serde_json::from_value(expected).unwrap();
            assert_eq!(got, restored);
            println!("{args} -> {}", serde_json::to_string(&got).unwrap());
        }
    }

    #[test]
    fn rejects_nonconforming_arguments_before_computing() {
        for arg in [
            json!({}),
            json!(null),
            json!([]),
            json!("a"),
            json!({"text":1}),
            json!({"text":null}),
            json!({"text":"a","extra":true}),
        ] {
            assert!(response("synthetic-invalid".into(), &arg).is_err());
        }
    }
}
