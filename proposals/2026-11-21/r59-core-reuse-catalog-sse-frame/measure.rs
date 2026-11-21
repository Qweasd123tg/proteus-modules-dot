// Same serializer as stock, isolated allocation accounting for repeated frames.
use super::*;
use crate::r59_alloc::measure;
use std::hint::black_box;

fn stock_catalog_update_frame() -> Frame<Bytes> {
    Frame::data(encode_sse_output(&StdioOutput::Event {
        event: Box::new(AppServerEvent::SessionCatalogUpdated),
    }))
}

fn bytes_of(frame: Frame<Bytes>) -> Bytes {
    frame.into_data().expect("catalog notification is data")
}

#[test]
fn r59_catalog_update_frame_is_exact_and_reused() {
    let (stock, old_once) = measure(|| bytes_of(stock_catalog_update_frame()));
    let (cached, new_once) = measure(|| bytes_of(catalog_update_frame()));
    assert_eq!(stock, cached);
    let frame = std::str::from_utf8(&cached).unwrap();
    let json = frame
        .strip_prefix("event: output\ndata: ")
        .and_then(|s| s.strip_suffix("\n\n"))
        .unwrap();
    let parsed = serde_json::from_str::<StdioOutput>(json).unwrap();
    assert!(matches!(
        parsed, StdioOutput::Event { event } if matches!(*event, AppServerEvent::SessionCatalogUpdated)
    ));
    println!(
        "r59 first_observed calls {}->{}, bytes {}->{}, frame {}",
        old_once.calls,
        new_once.calls,
        old_once.bytes,
        new_once.bytes,
        cached.len()
    );

    for n in [1, 16, 256, 1024] {
        let (_, a) = measure(|| {
            for _ in 0..n {
                black_box(stock_catalog_update_frame());
            }
        });
        let (_, b) = measure(|| {
            for _ in 0..n {
                black_box(catalog_update_frame());
            }
        });
        assert!(a.calls > 0 && a.bytes > 0);
        assert_eq!((b.calls, b.bytes), (0, 0), "{n} framed notifications");
        println!(
            "r59 repeated_{n} calls {}->{}, bytes {}->{}",
            a.calls, b.calls, a.bytes, b.bytes
        );
    }

    // Independent consumers can retain or drop a frame without changing later copies.
    std::thread::scope(|scope| {
        for _ in 0..4 {
            let expected = cached.clone();
            scope.spawn(move || {
                for _ in 0..16 {
                    assert_eq!(bytes_of(catalog_update_frame()), expected);
                }
            });
        }
    });
    let data = std::env::var("R59_CATALOG_FRAME").unwrap();
    std::fs::write(data, cached).unwrap();
}
