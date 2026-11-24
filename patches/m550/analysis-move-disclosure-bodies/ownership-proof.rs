#[cfg(test)]
mod m550_model_disclosure_identity {
    use super::*;

    #[test]
    fn owned_tight_loose_and_empty_policy_matches_previous_borrowed_input() {
        for (key, body, spare) in [
            ("x:answer", "🦀 Ж\r\n \"test\" \0\u{85}", 0),
            ("x:message-0", "Ж\u{2029}\r\n", 100_000),
            ("x:tools", "", 0),
            ("x:instructions", "", 100_000),
        ] {
            let mut owned = String::with_capacity(body.len() + spare);
            owned.push_str(body);
            let ptr = owned.as_ptr();
            let expected = disclosure(key, "Title", &Value::from(body), &Open);
            let actual = disclosure_text(key, "Title", owned, &Open);
            assert_eq!(actual.to_string(), expected.to_string());
            let Value::String(text) = &actual["children"][0]["text"] else {
                panic!()
            };
            assert_eq!(text.capacity(), text.len());
            if !body.is_empty() {
                assert_eq!(text.as_ptr() == ptr, spare == 0);
            }
        }
    }
}
