// Isolate the cold-route Vec expression on the actual Contracts type; this is NOT a replay/PSS benchmark.
use proteus_contracts::app_protocol::AppTranscriptMessage;
use std::{hint::black_box, mem::size_of};
fn rows(n: usize) -> Vec<AppTranscriptMessage> {
    let mut rows = Vec::new();
    for i in 0..n {
        rows.push(AppTranscriptMessage {
            message_id: Some(proteus_contracts::domain::MessageId::from_u128(i as u128 + 1)),
            timestamp_ms: Some((i / 100) as i64),
            phase: None, role: if i%2==0 { "user" } else { "assistant" }.into(), text: format!("row {i}"),
            images: vec![], tool: None, subagent: None, streaming: false,
        });
    }
    rows
}
fn main() {
    let n=125000usize;
    println!("rows={n} stride={}", size_of::<AppTranscriptMessage>());
    for end in [n, 65000, 0] {
        let start=end.saturating_sub(50);
        for stock in [true, false] {
            let full=black_box(rows(n));
            let input=full.capacity();
            let selected=full.into_iter().skip(black_box(start)).take(black_box(end-start));
            let window:Vec<_>=if stock { selected.collect() } else {
                let mut window=Vec::with_capacity(end-start);
                window.extend(selected);
                window
            };
            assert_eq!(window.len(),end-start);
            for (row,i) in window.iter().zip(start..end) {
                assert_eq!(row.message_id.unwrap().as_u128(),i as u128+1);
                assert_eq!(row.role,if i%2==0 {"user"} else {"assistant"});
                assert_eq!(row.text,format!("row {i}"));
            }
            if !stock {assert!(window.capacity()<=50);}
            println!("variant={} before={} archive_capacity={} page_len={} page_capacity={} page_slab_bytes={}",if stock {"stock"} else {"window"},end,input,window.len(),window.capacity(),window.capacity()*size_of::<AppTranscriptMessage>());
        }
    }
}
