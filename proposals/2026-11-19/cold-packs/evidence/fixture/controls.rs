// Supplemental only: ordinary authenticated history routes, no cache internals.
#[cfg(unix)]
async fn r12_get(state: &HttpAppState, uri: &str, expected: StatusCode) -> Bytes {
    let res = route_request(state.clone(), authed_get_request(uri))
        .await
        .unwrap();
    let status = res.status();
    let bytes = response_bytes(res).await;
    assert_eq!(
        status,
        expected,
        "{uri}: {}",
        String::from_utf8_lossy(&bytes[..bytes.len().min(512)])
    );
    bytes
}

#[cfg(unix)]
async fn r12_page(
    state: &HttpAppState,
    query: &str,
    revision: &str,
    before: usize,
    export: &[Value],
) -> usize {
    let uri = format!("/history/page?{query}&before={before}&revision={revision}");
    let raw = r12_get(state, &uri, StatusCode::OK).await;
    let page: Value = serde_json::from_slice(&raw).unwrap();
    let start = before.saturating_sub(50);
    assert_eq!(page["start"], start);
    assert_eq!(page["revision"], revision);
    assert_eq!(page["total"], export.len());
    assert_eq!(page["messages"].as_array().unwrap(), &export[start..before]);
    start
}

#[cfg(unix)]
async fn r12_scroll(state: &HttpAppState, query: &str, rev: &str, export: &[Value]) {
    use std::time::Instant;
    let n = export.len();
    // Run oldest and cross-pack arbitrary offsets before warming all packs by scrolling.
    let sparse = Instant::now();
    for end in [0, 1, 49, 50, 51, 399, 400, 401, 417, n.saturating_sub(49)] {
        if end <= n {
            r12_page(state, query, rev, end, export).await;
        }
    }
    let sparse_ms = sparse.elapsed().as_secs_f64() * 1e3;
    let walk = Instant::now();
    let mut end = n;
    let mut pages = 0;
    while end != 0 {
        end = r12_page(state, query, rev, end, export).await;
        pages += 1;
    }
    eprintln!(
        "R12_SCROLL total={n} pages={pages} sampled_ms={sparse_ms:.3} walk_ms={:.3}",
        walk.elapsed().as_secs_f64() * 1e3
    );
}

#[cfg(unix)]
async fn r12_export(state: &HttpAppState, query: &str) -> (Bytes, Vec<Value>) {
    let start = std::time::Instant::now();
    let raw = r12_get(state, &format!("/history?{query}"), StatusCode::OK).await;
    let elapsed = start.elapsed();
    let rows: Vec<Value> = serde_json::from_slice(&raw).unwrap();
    eprintln!(
        "R12_EXPORT rows={} bytes={} wall_ms={:.3}",
        rows.len(),
        raw.len(),
        elapsed.as_secs_f64() * 1e3
    );
    (raw, rows)
}
