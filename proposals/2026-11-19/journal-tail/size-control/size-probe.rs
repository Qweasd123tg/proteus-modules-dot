
#[cfg(test)]
mod perf8_size_probe {
    use super::*;
    use serde_json::{Value, json};
    #[test]
    fn counting_matches_materialization() {
        let cases = [
            Value::Null,
            json!({"строка":"\n\r\\\"\t\0\u{001f}東京 😃", "bool":true, "f":[1.5,0.0,-0.0,1e300,1e-300],"empty":{},"seq":[]}),
            serde_json::from_str(r#"{"duplicate":1,"duplicate":100,"raw":"\u0440","f":1.000e3}"#).unwrap(),
            json!({"test":[0, -1, i64::MIN, u64::MAX]}),
            json!({"fixture": (0..3000).map(|i| format!("{i} \"\\\n\t 漢字")).collect::<Vec<_>>() }),
        ];
        for value in cases {
            assert_eq!(encoded_json_len(&value).unwrap(), serde_json::to_vec(&value).unwrap().len());
        }
    }
}
