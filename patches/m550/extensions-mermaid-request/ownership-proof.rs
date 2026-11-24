#[cfg(test)]
mod m550_exact_key {
    use super::*;
    use serde_json::json;

    #[test]
    fn live_worker_moves_the_original_large_cache_key_and_recovers_valid_followup() {
        let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("worker.mjs");
        let mut worker = Worker::start(&script).unwrap();
        let source = "flowchart LR\r\nА[Привет]-->B[🦀]";
        let theme = json!({
            "foreground":"#dddddd","background":"#181818","accent":"#99aaff",
            "muted":"#999999","border":"#555555","danger":"#ff9999",
            "surface":"#222222","surface_alt":"#333333",
            "font_family":"sans-serif","font_family_mono":"monospace",
            "synthetic_unused_padding":"я🦀".repeat(81_000)
        });
        for (i, source) in [source, "unsupported Привет", source]
            .into_iter()
            .enumerate()
        {
            let key = crate::render_request(source, Some(&theme)).unwrap();
            assert!((480_000..=512 * 1024).contains(&key.len()));
            let identity = (key.as_ptr(), key.len(), key.capacity());
            let expected = key.clone(); // assertion copy, outside the production worker.
            if i == 1 {
                let problem = worker.render(key).unwrap_err().to_string();
                assert!(!problem.is_empty());
                continue;
            }
            let (returned, svg) = worker.render(key).unwrap();
            assert_eq!(returned, expected);
            assert_eq!(
                (returned.as_ptr(), returned.len(), returned.capacity()),
                identity
            );
            assert_eq!(svg["type"], "svg");
            assert!(svg["source"].as_str().unwrap().contains("Привет"));
            println!(
                "worker preserved exact pointer, length and capacity for {} bytes",
                returned.len()
            );
        }
    }
}
