use super::*;

#[test]
fn r277_blob_shell_failure_restores_donor() {
    for shape in 0..5 {
        let response = SessionStorageResponse::BlobData {
            blob: blob(),
            data_base64: payload(64, 64),
        };
        let want = serde_json::to_vec(&serde_json::to_value(&response).unwrap()).unwrap();
        let got = serialize_blob_response(response, |empty| {
            let SessionStorageResponse::BlobData { data_base64, .. } = empty else {
                panic!()
            };
            assert!(data_base64.is_empty());
            match shape {
                0 => Err(<serde_json::Error as serde::ser::Error>::custom(
                    "shell failed",
                )),
                1 => Ok(Value::Null),
                2 => Ok(json!({})),
                3 => Ok(json!({"data_base64":null})),
                4 => Ok(json!({"data_base64":"not empty"})),
                _ => unreachable!(),
            }
        })
        .unwrap();
        assert_eq!(serde_json::to_vec(&got).unwrap(), want);
    }
}
