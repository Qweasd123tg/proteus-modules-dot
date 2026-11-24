use super::*;
use crate::meter;
use std::{
    hash::{DefaultHasher, Hash, Hasher},
    path::Path,
};

fn workspace() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
}
fn expected_log(profile: &str) -> String {
    if profile == "empty" {
        return String::new();
    }
    let padding = "x".repeat(if profile == "tiny" { 2 } else { 97000 });
    (5..65)
        .map(|i| match i {
            8 => "token <token> logged invalid byte: �".to_owned(),
            60 => String::new(),
            _ => format!("fixture {i:02} {padding}"),
        })
        .collect::<Vec<_>>()
        .join("\n")
}
fn await_exit(b: &mut Backend) {
    let deadline = Instant::now() + Duration::from_secs(5);
    while !b.stderr.is_finished() || b.child.try_wait().unwrap().is_none() {
        assert!(
            Instant::now() < deadline,
            "synthetic app-server did not finish"
        );
        thread::yield_now();
    }
}
fn emit(label: &str, c: meter::Count, text: &str) {
    let mut h = DefaultHasher::new();
    text.as_bytes().hash(&mut h);
    println!(
        "M411_DIAG {label} {} {} {} {} {} {} {}",
        c.requests,
        c.bytes,
        c.live,
        c.peak,
        c.largest,
        text.len(),
        h.finish()
    )
}
#[test]
fn ready_supervisor_formats_real_exited_backend_and_redacted_ring() {
    for profile in ["empty", "tiny", "large"] {
        let mut backend = Backend::launch(Some(profile), workspace(), None).unwrap();
        assert_eq!(backend.origin, "http://127.0.0.1:7");
        await_exit(&mut backend);
        let (payload, alloc) = meter::measure(|| backend.exit_report());
        let payload = payload.unwrap();
        assert_eq!(
            payload,
            format!("server exited (exit status: 7)\n{}", expected_log(profile))
        );
        emit(profile, alloc, &payload);
    }
}
#[test]
fn pre_ready_failure_keeps_the_identical_error_message() {
    let error = match Backend::launch(Some("died-before-ready"), workspace(), None) {
        Ok(_) => panic!("pre-ready failure turned into a connection"),
        Err(e) => e,
    };
    let text = format!("{error:#}");
    assert_eq!(
        text,
        format!(
            "server exited before it was ready (exit status: 7)\n{}",
            expected_log("died-before-ready")
        )
    );
    let mut h = DefaultHasher::new();
    text.as_bytes().hash(&mut h);
    println!("M411_STARTUP {} {}", text.len(), h.finish());
}

#[test]
fn startup_still_rejects_a_non_origin_ready_record() {
    let report = match Backend::launch(Some("invalid-origin"), workspace(), None) {
        Ok(_) => panic!("invalid origin was permitted"),
        Err(error) => format!("{error:#}"),
    };
    assert_eq!(
        report,
        "server reported invalid origin: origin must not contain a path, query, or fragment"
    );
}
