#[cfg(test)]
include!("counter.rs");

#[cfg(test)]
mod proof {
    use proteus_tabs::{Edge, Node, Pane, PaneId, Size, TabLayout};
    use serde_json::{Value, json};
    use std::hint::black_box;
    include!("lifted.rs");

    const A: &str = "chat:/fixture/левый";
    const B: &str = "codex:opaque:right";
    const C: &str = "files:old/é.rs";
    const D: &str = "git:summary";
    fn one() -> TabLayout {
        let mut l = TabLayout::default();
        l.open(A, |_| false);
        l
    }
    fn two() -> TabLayout {
        let mut l = one();
        l.open_in(B, PaneId(0), |_| false);
        l.split(B, PaneId(0), Edge::Right);
        l
    }
    fn grid() -> TabLayout {
        let mut l = two();
        l.open_in(C, PaneId(0), |_| false);
        l.split(C, PaneId(0), Edge::Bottom);
        l.open_in(D, PaneId(1), |_| false);
        l.split(D, PaneId(1), Edge::Bottom);
        l
    }
    fn wide() -> TabLayout {
        let mut l = one();
        for i in 1..12 {
            let tab = format!("files:ordinary/{i}.rs");
            l.open_in(&tab, PaneId(0), |_| false);
            l.split(&tab, PaneId(0), Edge::Right);
        }
        l
    }
    fn lock_holder() -> TabLayout {
        let mut l = two();
        l.lock_pane(PaneId(1), true, 1200., 800., 0.);
        l.close(A);
        let p = l.pane(PaneId(0)).unwrap();
        assert!(p.tabs.is_empty() && l.holds_room(p.id));
        assert_eq!(l.pane_locked(PaneId(1)), Some(true));
        l
    }

    fn posted(label: &str, l: TabLayout, expected_n: usize, valid: bool) {
        let before = l.clone();
        assert_eq!(l.validate().is_ok(), valid);
        let panes = l.panes();
        let ids = panes.iter().map(|p| p.id.0).collect::<Vec<_>>();
        let (count, count_calls, count_bytes) = crate::measurement(|| black_box(&l).pane_count());
        assert_eq!(count, expected_n);
        assert_eq!(count, panes.len()); // original independent result; outside scope
        let mut buttons = Vec::with_capacity(count);
        let (_, control_calls, control_bytes) = crate::measurement(|| {
            for p in &panes {
                buttons.push(black_box(render_controls_closeable(
                    black_box(p),
                    black_box(&l),
                )));
            }
        });
        if matches!(label, "single" | "empty-single") {
            assert_eq!(buttons, [false]);
        }
        if matches!(label, "two" | "grid" | "wide" | "locked-holder") {
            assert!(buttons.iter().all(|&b| b));
        }
        if label == "locked-empty" {
            assert_eq!(buttons, [true, false]);
        }
        let missing = l.can_close(PaneId(u32::MAX));
        assert_eq!(missing, count > 1); // historical query result, not closing semantics
        let order = valid.then(|| {
            l.rects_spaced(1260., 880., 5.)
                .iter()
                .map(|(id, r)| {
                    (
                        id.0,
                        [r.x.to_bits(), r.y.to_bits(), r.w.to_bits(), r.h.to_bits()],
                    )
                })
                .collect::<Vec<_>>()
        });
        assert_eq!(l, before);
        let serialized = serde_json::to_string(&l).unwrap();
        assert_eq!(serialized, serde_json::to_string(&before).unwrap());
        eprintln!(
            "TRACE {label} {}",
            json!({"count":count,"ids":ids,"closable":buttons,
                   "missing":missing,"valid":valid,"geometry_bits":order,"saved":serialized})
        );
        eprintln!(
            "WORK {label} {}",
            json!([
                count,
                count_calls,
                count_bytes,
                control_calls,
                control_bytes
            ])
        );
    }

    #[test]
    fn real_open_split_layout_and_controls() {
        eprintln!("ARM {}", env!("R117_ARM"));
        posted("single", one(), 1, true);
        posted("two", two(), 2, true);
        posted("grid", grid(), 4, true);
        posted("wide", wide(), 12, true);
    }
    #[test]
    fn existing_empty_and_locked_layout_controls() {
        posted("empty-single", TabLayout::default(), 1, true);
        posted("locked-holder", lock_holder(), 2, true);
        let all_empty = json!({"split":{"axis":"row","children":[
          {"size":{"fixed":240.},"node":{"pane":{"id":0,"tabs":[],"pinned":0,"active":null,"locked":true}}},
          {"size":{"weight":1.},"node":{"pane":{"id":1,"tabs":[],"pinned":0,"active":null}}}
        ]}});
        posted("locked-empty", layout(all_empty, 2), 2, true);
        let mut empty_fixed = lock_holder();
        let Node::Split(ref mut root) = empty_fixed.root else {
            unreachable!()
        };
        root.children[0].size = Size::Fixed(240.);
        root.children[1].size = Size::Weight(1.);
        // Legal Rust representation, intentionally not admitted to the persisted model.
        posted("empty-fixed-transient", empty_fixed, 2, false);
    }
    fn layout(root: Value, next_id: u32) -> TabLayout {
        serde_json::from_value(json!({"root":root,"focused":0,"next_id":next_id})).unwrap()
    }
    #[test]
    fn transient_empty_split_and_duplicate_leaf_ids_keep_exact_count() {
        let empty = json!({"split":{"axis":"row","children":[]}});
        posted("empty-split", layout(empty.clone(), 1), 0, false);
        let leaf = json!({"pane":{"id":0,"tabs":[],"pinned":0,"active":null}});
        let nested = json!({"split":{"axis":"row","children":[
            {"size":{"weight":1.},"node":empty},
            {"size":{"weight":2.},"node":{"split":{"axis":"column","children":[
                {"size":{"fixed":250.},"node":leaf},
                {"size":{"weight":1.},"node":leaf}
            ]}}}
        ]}});
        posted("duplicate-nested", layout(nested, 2), 2, false);
    }
}
