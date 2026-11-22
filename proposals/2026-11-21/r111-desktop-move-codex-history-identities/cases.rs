use crate::agents::codex::{Item, ItemKind, projection};
use crate::transcript::{Change, Transcript};
use serde_json::{Value, json};
use std::sync::Arc;

fn ordinary_id(i: usize) -> String {
    format!("item-00000000-0000-4000-8000-00000000{i:04}")
}
fn ordinary_turn(i: usize) -> String {
    format!("turn-00000000-0000-4000-8000-00000000{:04}", i / 5)
}
fn projected(i: usize) -> Item {
    let id = ordinary_id(i);
    let turn = ordinary_turn(i);
    let value = match i % 5 {
        0 => json!({"id":id,"type":"agentMessage","text":format!("résumé {i} 🦀")}),
        1 => {
            json!({"id":id,"type":"userMessage","content":[{"text":"input 東京"},{"text":i.to_string()}]})
        }
        2 => {
            json!({"id":id,"type":"reasoning","summary":[{"text":"visible summary"}],"content":["not read"]})
        }
        3 => {
            json!({"id":id,"type":"fileChange","changes":[{"path":"sample/é.txt","kind":{"type":"update"},"diff":"@@ -1 +1 @@\n-context\n+🦀"}]})
        }
        _ => {
            json!({"id":id,"type":"dynamicToolCall","tool":"shape_only","arguments":{"z":"é","a":[0,null,false]},"contentItems":[{"type":"text","text":"résumé\t😀"}]})
        }
    };
    projection::item(&value, turn.as_str(), true, Some(1_000 + i as i64)).unwrap()
}
fn item(turn: &str, id: &str, text: &str, streaming: bool, time: Option<i64>) -> Item {
    Item {
        id: id.into(),
        turn_id: turn.into(),
        kind: ItemKind::Assistant { text: text.into() },
        status: if streaming {
            "inProgress".into()
        } else {
            "completed".into()
        },
        timestamp_ms: time,
    }
}
fn splice(inserted: usize) -> Change {
    Change::Spliced {
        start: 0,
        removed: 0,
        inserted,
    }
}
fn measured(label: &str, archive: &mut Transcript, page: Vec<Item>) -> Change {
    let fixtures = page.len();
    let nonempty_ids = page
        .iter()
        .map(|p| usize::from(!p.turn_id.is_empty()) + usize::from(!p.id.is_empty()))
        .sum::<usize>();
    let id_bytes = page
        .iter()
        .map(|p| p.turn_id.len() + p.id.len())
        .sum::<usize>();
    let (change, calls, bytes) =
        crate::measurement(|| archive.external_prepend(std::hint::black_box(page)));
    eprintln!(
        "WORK {label} {}",
        json!([fixtures, nonempty_ids, id_bytes, calls, bytes])
    );
    change
}
fn rows(archive: &Transcript) -> Vec<Value> {
    archive
        .entries()
        .iter()
        .map(|entry| {
            let (turn, id) = archive.external_identity(entry.key).unwrap();
            assert!(archive.external_contains(turn, id));
            json!({"key":entry.key,"identity":[turn,id],"role":format!("{:?}",entry.role),
          "text":entry.text.as_ref(),"message_id":entry.message_id,"streaming":entry.streaming,
          "time":entry.time,"images":entry.images,"tool":entry.tool,"subagent":entry.subagent,
          "retained_bytes":entry.retained_bytes()})
        })
        .collect()
}
fn trace(label: &str, archive: &Transcript, change: Change) {
    let row = json!({"change":format!("{change:?}"),"rows":rows(archive),
         "first_identity":archive.external_first_identity()});
    eprintln!("TRACE {label} {row}");
}

#[test]
fn ordinary_real_projection_page_mixed_with_archive_overlap() {
    eprintln!("ARM {}", env!("R111_ARM"));
    let mut archive = Transcript::default();
    for i in 45..50 {
        // These five rows overlap but must keep the prior payload, role and time.
        archive.external_upsert(item(
            &ordinary_turn(i),
            &ordinary_id(i),
            "archive wins",
            false,
            Some(7),
        ));
    }
    archive.external_upsert(item("tail-turn", "tail-item", "current tail", true, None));
    let old = rows(&archive);
    let preserved = archive
        .entries()
        .iter()
        .map(|e| Arc::clone(&e.text))
        .collect::<Vec<_>>();
    let page = (0..50).map(projected).collect::<Vec<_>>();

    // Independent reference builds existing-row retention + accepted page first, by
    // singleton upserts; all keys must come from the same seeded counter.
    let mut separate = Transcript::default();
    for _ in 45..51 {
        separate.external_upsert(item("seed", "counter-seed", "seed", false, None));
        assert_eq!(
            separate.external_remove("seed", "counter-seed"),
            Change::Spliced {
                start: 0,
                removed: 1,
                inserted: 0
            }
        );
    }
    for p in &page[..45] {
        assert_eq!(separate.external_upsert(p.clone()), Change::Pushed);
    }
    let mut expected = rows(&separate);
    expected.extend(old);

    let change = measured("ordinary-50", &mut archive, page);
    assert_eq!(change, splice(45));
    assert_eq!(rows(&archive), expected);
    for (e, ptr) in archive.entries()[45..].iter().zip(preserved) {
        assert!(Arc::ptr_eq(&e.text, &ptr));
    }
    trace("ordinary-50", &archive, change);
    let file = &archive.entries()[3].tool.as_ref().unwrap();
    assert_eq!(file.call_id, ordinary_id(3));
    assert_eq!(file.name, "apply_patch");
    assert_eq!(file.args[0]["diff"], "@@ -1 +1 @@\n-context\n+🦀");
    let dynamic = &archive.entries()[4].tool.as_ref().unwrap();
    assert_eq!(dynamic.args.to_string(), r#"{"z":"é","a":[0,null,false]}"#);
    assert_eq!(
        dynamic.result.as_deref(),
        Some(r#"[{"type":"text","text":"résumé\t😀"}]"#)
    );

    assert_eq!(
        archive.external_upsert(item("later-turn", "later-item", "after", false, Some(17))),
        Change::Pushed
    );
    assert_eq!(archive.entries().last().unwrap().key, 52);
    let victim = archive.entries()[0].key;
    assert_eq!(
        archive.external_trim_budget(51, usize::MAX).0,
        Change::Spliced {
            start: 0,
            removed: 1,
            inserted: 0
        }
    );
    archive.external_prune();
    assert!(archive.external_identity(victim).is_none());
    assert!(!archive.external_contains(&ordinary_turn(0), &ordinary_id(0)));
    let reinsert = archive.external_prepend(vec![projected(0)]);
    assert_eq!(reinsert, splice(1));
    assert_eq!(archive.entries()[0].key, 53);
    trace("prune-and-reinsert", &archive, reinsert);
}

#[test]
fn all_overlap_empty_and_still_live_archive_key() {
    let mut archive = Transcript::default();
    for i in 0..50 {
        archive.external_upsert(projected(i));
    }
    let old = rows(&archive);
    let page = (0..50)
        .map(|i| {
            item(
                &ordinary_turn(i),
                &ordinary_id(i),
                "must not replace",
                true,
                None,
            )
        })
        .collect();
    let change = measured("all-overlap-50", &mut archive, page);
    assert_eq!(change, splice(0));
    assert_eq!(rows(&archive), old);
    trace("all-overlap-50", &archive, change);
    let empty = measured("empty-page", &mut archive, vec![]);
    assert_eq!(empty, splice(0));
    assert_eq!(rows(&archive), old);
    assert_eq!(
        archive.external_upsert(item("other-turn", "other-item", "new", false, None)),
        Change::Pushed
    );
    assert_eq!(archive.entries().last().unwrap().key, 51);
    trace("empty-then-upsert", &archive, empty);
}

#[test]
fn duplicate_rows_empty_unicode_ids_and_stale_archive_mapping() {
    let mut archive = Transcript::default();
    archive.external_upsert(item("keep", "key", "still here", false, None));
    archive.external_upsert(item("stale", "id", "removed without prune", false, None));
    let stale = archive.entries()[1].key;
    assert_eq!(
        archive.remove(1..2),
        Change::Spliced {
            start: 1,
            removed: 1,
            inserted: 0
        }
    );
    assert!(!archive.external_contains("stale", "id"));
    assert_eq!(archive.external_identity(stale), Some(("stale", "id"))); // mapping remains until upsert/prune
    let empty_ids = measured(
        "empty-ids",
        &mut archive,
        vec![item("", "", "empty", false, None)],
    );
    assert_eq!(empty_ids, splice(1));
    assert_eq!(archive.entries()[0].key, 3);
    let history = vec![
        item("т:1", "識別子🦀", "start", true, Some(23)),
        item("т:1", "識別子🦀", "completed", false, None),
        item("т:2", "識別子🦀", "same id different turn", false, Some(25)),
        item("т:1", "識別子🦀", "stale streaming", true, Some(88)),
        item("", "only-id", "empty turn", false, None),
        item("only-turn", "", "empty item", false, None),
        item("stale", "id", "reintroduced", false, None),
        item("", "", "archived empty must win", false, None),
    ];
    let change = measured("duplicate-unicode-missing", &mut archive, history);
    assert_eq!(change, splice(5));
    assert_eq!(
        archive.entries().iter().map(|e| e.key).collect::<Vec<_>>(),
        vec![4, 5, 6, 7, 8, 3, 1]
    );
    assert_eq!(
        archive
            .entries()
            .iter()
            .map(|e| e.text.as_ref())
            .collect::<Vec<_>>(),
        vec![
            "completed",
            "same id different turn",
            "empty turn",
            "empty item",
            "reintroduced",
            "empty",
            "still here"
        ]
    );
    assert_eq!(archive.entries()[0].time, Some(23));
    assert!(!archive.entries()[0].streaming);
    assert_eq!(archive.external_identity(stale), None); // append updates the same map entry
    archive.external_prune();
    assert_eq!(
        archive.external_upsert(item("end", "end", "next", false, None)),
        Change::Pushed
    );
    assert_eq!(archive.entries().last().unwrap().key, 9);
    trace("duplicate-unicode-missing", &archive, change);
}
