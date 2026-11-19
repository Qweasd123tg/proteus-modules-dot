
#[test]
#[ignore = "manual CompareSnapshots benchmark; no model or network"]
fn perf7_compare() {
    let lengths = std::env::var("PERF7_LENGTHS").unwrap_or_else(|_| "128,512".into());
    for n in lengths.split(',').map(|n| n.parse::<usize>().unwrap()) {
        for kind in backends() {
            let mut f = Fixture::new(kind);
            let body = "x".repeat(704);
            for i in 0..n { f.append(vec![text(&format!("{i}:{body}"))]); }
            let old = f.snapshot();
            f.service.execute(SessionStorageRequest::ReleaseSnapshot { snapshot: old.clone() }).unwrap();
            f.append(vec![text("one small tail")]);
            crate::diagnostics::reset();
            let open_time = Instant::now();
            let new = f.snapshot();
            let open_ns = open_time.elapsed().as_nanos();
            let opened = crate::diagnostics::get().decoded;
            for iter in 0..3 {
                let request = SessionStorageRequest::CompareSnapshots { snapshot: new.clone(), prefix: old.clone() };
                crate::diagnostics::reset();
                let now = Instant::now();
                let actual = f.service.execute(request).unwrap();
                let cmp_ns = now.elapsed().as_nanos();
                assert_eq!(actual, SessionStorageResponse::SnapshotPrefix { matches: true });
                let cost = crate::diagnostics::get();
                eprintln!("SAMPLE,{kind:?},{n},{iter},{open_ns},{opened},{cmp_ns},{},{}",cost.decoded,cost.fingerprint_bytes);
            }
        }
    }
}
