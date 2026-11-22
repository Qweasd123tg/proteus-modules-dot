#[cfg(test)]
include!("counter.rs");

#[cfg(test)]
mod proof {
    use proteus_tabs::{Node, Pane, PaneId, TabLayout};
    use serde_json::json;
    use std::hint::black_box;

    const A: &str = "files:/src/alpha-ёж.rs";
    const B: &str = "diff:/src/βeta-日本語.rs";
    const C: &str = "files:/src/😺.rs";
    const D: &str = "files:/preview/first.rs";
    const E: &str = "files:/preview/next.rs";
    const CHAT: &str = "chat:/fixture/контекст";
    const MISSING: &str = "files:/not-present";

    fn tree_pane(layout: &TabLayout) -> &Pane {
        let Node::Pane(ref pane) = layout.root else {
            panic!("one pane required")
        };
        pane
    }

    fn tree_pane_mut(layout: &mut TabLayout) -> &mut Pane {
        let Node::Pane(ref mut pane) = layout.root else {
            panic!("one pane required")
        };
        pane
    }

    fn plain(ids: &[&str]) -> Pane {
        let mut pane = Pane::new(PaneId(0));
        pane.tabs = ids.iter().map(|id| (*id).to_owned()).collect();
        pane
    }

    fn exact_history(pane: &Pane, expected: &[&str]) -> String {
        // The actual Pane derives Debug, which includes its private history;
        // unlike the serde wire this witnesses history even when all tabs fit.
        let printed = format!("{pane:?}");
        let suffix = format!("history: {expected:?} }}");
        assert!(
            printed.ends_with(&suffix),
            "{printed} does not end in {suffix}"
        );
        printed
    }

    fn measure(label: &str, pane: &mut Pane, ids: &[&str]) {
        let (_, requests, bytes) = crate::measurement(|| {
            for &id in ids {
                black_box(&mut *pane).show(black_box(id));
            }
        });
        let text_bytes = ids.iter().map(|id| id.len()).sum::<usize>();
        eprintln!(
            "WORK {label} {}",
            json!([ids.len(), text_bytes, requests, bytes])
        );
    }

    #[test]
    fn ordinary_repeated_revisits_first_restored_active_and_missing() {
        eprintln!("ARM {}", env!("R128_ARM"));
        let mut same = plain(&[A, B]);
        same.show(B);
        same.show(A);
        measure("same-active", &mut same, &[A; 64]);
        assert_eq!(same.active.as_deref(), Some(A));
        let same = exact_history(&same, &[B, A]);

        let mut alternating = plain(&[A, B]);
        alternating.show(B);
        alternating.show(A);
        let alt = [B, A].repeat(32);
        measure("alternate", &mut alternating, &alt);
        assert_eq!(alternating.active.as_deref(), Some(A));
        let alternating = exact_history(&alternating, &[B, A]);

        let mut first = plain(&[A, B]);
        first.show(A); // reserve the ordinary history vec outside the measurement
        measure("first-visit", &mut first, &[B]);
        assert_eq!(first.active.as_deref(), Some(B));
        let first = exact_history(&first, &[A, B]);

        let serialized = serde_json::to_string(&plain_with_active(A)).unwrap();
        let mut restored: Pane = serde_json::from_str(&serialized).unwrap();
        exact_history(&restored, &[]);
        measure("restored-active", &mut restored, &[A]);
        assert_eq!(restored.active.as_deref(), Some(A));
        assert_eq!(serde_json::to_string(&restored).unwrap(), serialized);
        let restored = exact_history(&restored, &[A]);

        let mut missing = plain_with_active(A);
        let before = missing.clone();
        measure("missing", &mut missing, &[MISSING; 64]);
        assert_eq!(missing, before);
        let missing = exact_history(&missing, &[A]);

        eprintln!(
            "TRACE branch-local {}",
            json!({
                "same":same,"alternate":alternating,"first":first,"restored":restored,"missing":missing
            })
        );
    }

    fn plain_with_active(id: &str) -> Pane {
        let mut p = plain(&[A, B]);
        p.show(id);
        p
    }

    #[test]
    fn actual_layout_switch_pin_preview_replace_and_close_mru_fallback() {
        let mut l = TabLayout::default();
        for id in [CHAT, A, B, C] {
            l.open(id, |_| false);
        }
        l.set_pinned(A, true);
        l.open_preview(D, |_| false);
        l.activate(PaneId(0), B);
        l.activate(PaneId(0), B);
        assert_eq!(l.preview.as_deref(), Some(D));
        assert_eq!(l.active_chat(None).as_deref(), Some(CHAT));
        assert!(l.is_pinned(A));
        let mut lifecycle = Vec::new();
        let mut save = |state: &TabLayout, name, want, history: &[&str]| {
            assert_eq!(state.active(PaneId(0)), Some(want), "{name}");
            assert!(state.validate().is_ok());
            assert!(state.is_pinned(A));
            let debug = exact_history(tree_pane(state), history);
            let serialized = serde_json::to_string(state).unwrap();
            let roundtrip: TabLayout = serde_json::from_str(&serialized).unwrap();
            assert_eq!(serde_json::to_string(&roundtrip).unwrap(), serialized);
            lifecycle.push(
                json!({"name":name,"active":want,"layout":serialized,"pane":debug,
                                    "closed":state.closed_ids().collect::<Vec<_>>()}),
            );
        };
        save(&l, "revisit-pinned-preview", B, &[CHAT, A, C, D, B]);
        l.open_preview(E, |_| false);
        assert_eq!(l.preview.as_deref(), Some(E));
        assert!(!l.contains(D));
        save(&l, "replace-preview", E, &[CHAT, A, C, B, E]);
        l.close(E);
        assert!(l.preview.is_none());
        save(&l, "close-preview-fallback", B, &[CHAT, A, C, B]);
        l.close(B);
        save(&l, "close-regular-fallback", C, &[CHAT, A, C]);
        eprintln!("TRACE layout-close {}", json!(lifecycle));
    }

    #[test]
    fn duplicate_mru_cleanup_removes_all_matches_and_preserves_other_order() {
        let other = "files:/retarget/stale-source";
        let mut l = TabLayout::default();
        for id in [A, B, other, D, E, C] {
            l.open(id, |_| false);
        }
        // Construct a controlled stale MRU using public exact types, without
        // instrumentation of the production module or raw memory access.
        let pane = tree_pane_mut(&mut l);
        pane.tabs.retain(|id| id != C);
        pane.active = Some(E.to_owned());
        l.retarget_document(A, C);
        tree_pane_mut(&mut l).tabs.retain(|id| id != C);
        l.retarget_document(other, C);
        assert!(l.validate().is_ok());
        let original = exact_history(tree_pane(&l), &[C, B, C, D, E, C]);

        let mut different = tree_pane(&l).clone();
        assert_eq!(different.active.as_deref(), Some(E));
        measure("duplicate-different", &mut different, &[C]);
        assert_eq!(different.active.as_deref(), Some(C));
        let changed = exact_history(&different, &[B, D, E, C]);

        let mut equal = tree_pane(&l).clone();
        equal.active = Some(C.to_owned());
        measure("duplicate-equal", &mut equal, &[C]);
        assert_eq!(equal.active.as_deref(), Some(C));
        let same = exact_history(&equal, &[B, D, E, C]);

        eprintln!(
            "TRACE duplicates {}",
            json!({"before":original,"different":changed,"equal":same})
        );
    }

    #[test]
    fn empty_string_tab_only_counts_when_exactly_present() {
        let mut p = plain(&[A]);
        p.show(A);
        let before = p.clone();
        p.show("");
        assert_eq!(p, before);
        p.tabs.push(String::new());
        p.show("");
        let warm = exact_history(&p, &[A, ""]);
        measure("empty-active", &mut p, &[""; 32]);
        assert_eq!(p.active.as_deref(), Some(""));
        assert_eq!(exact_history(&p, &[A, ""]), warm);
        eprintln!(
            "TRACE empty-id {}",
            json!({"exists":true,"active":p.active,"pane":warm})
        );
    }
}
