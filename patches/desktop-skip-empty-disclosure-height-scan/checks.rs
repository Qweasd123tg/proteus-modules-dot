#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Flow { Empty, First, Paging, Unchanged, Rewrite, EmptyCodex }

fn paired(flow: Flow, flags: u8) -> (Vec<Call>, usize, usize) {
    let a = stock::run(flow, flags);
    let b = candidate::run(flow, flags);
    let (c, before) = stock_counted::run(flow, flags);
    let (d, after) = candidate_counted::run(flow, flags);
    assert_eq!(a.0, b.0, "{flow:?} {flags}");
    assert_eq!(a.0, c, "counter perturbed stock effects");
    assert_eq!(a.0, d, "counter perturbed candidate effects");
    assert_eq!((a.1, b.1), (0, 0));
    (a.0, before, after)
}

#[test]
fn first_50_runs_rebase_with_empty_disclosures() {
    use Call::*;
    let (log, before, after) = paired(Flow::First, 0);
    assert_eq!((before, after), (50, 0));
    assert_eq!(log, vec![
        Update, Rebase(None), Update, Update, Invalidate(0..usize::MAX),
        Apply(Change::Spliced { start: 0, removed: 0, inserted: 50 }),
        Update, Archived(false), Update,
        Range(Some(HistoryRange { start: 950, rows: 50, total: 1000 }), false),
        Bind(None), Notify,
    ]);
    println!("first snapshot: 50 -> 0 row visits; full call trace equal");
}

#[test]
fn verified_live_rewrite_keeps_archive_and_scroller_update_at_200() {
    use Call::*;
    let (log, before, after) = paired(Flow::Rewrite, 0);
    assert_eq!((before, after), (200, 0));
    assert_eq!(log, vec![
        Update, Rebase(Some(949)), Update, Update, Invalidate(949..usize::MAX),
        Update, Archived(true), Update,
        Range(Some(HistoryRange { start: 750, rows: 200, total: 1000 }), false),
        Bind(None), Notify,
    ]);
    println!("archived rewrite: 200 -> 0 row visits; full call trace equal");
}

fn exclusions(log: Vec<Call>) -> Vec<(Range<usize>, usize)> {
    log.into_iter().filter_map(|c| match c {
        Call::Exclude(rows, total) => Some((rows, total)),
        _ => None,
    }).collect()
}

#[test]
fn each_disclosure_collection_blocks_guard_and_preserves_affected_ranges() {
    for (flags, want) in [
        (1, vec![(752..755, 1000)]),
        (2, vec![(756..760, 1000)]),
        (4, vec![(770..771, 1000)]),
        (8, vec![(756..764, 1000)]),
        (16, vec![(752..760, 1000)]),
        (32, vec![]),
        (64, vec![]),
        (128, vec![(760..764, 1000)]),
        (6, vec![(756..760, 1000), (770..771, 1000)]),
        (10, vec![(756..764, 1000)]),
        (19, vec![(752..760, 1000)]),
        (31, vec![(752..764, 1000), (770..771, 1000)]),
    ] {
        let (log, before, after) = paired(Flow::Rewrite, flags);
        assert_eq!((before, after), (200, 200), "flags {flags}");
        assert_eq!(exclusions(log), want, "flags {flags}");
    }
    println!("12 explicit exclusion controls; chain, terminal split, subagent peers, stale and invalid slot");
}

#[test]
fn all_256_disclosure_state_combinations_keep_effects_and_scan_only_when_required() {
    for flags in 0..=u8::MAX {
        let (_, before, after) = paired(Flow::Rewrite, flags);
        assert_eq!((before, after), (200, if flags == 0 { 0 } else { 200 }));
    }
    println!("256 disclosure combinations; complete scroller-call parity");
}

#[test]
fn no_scan_when_history_range_is_empty_and_update_is_not_called() {
    use Call::*;
    let (log, before, after) = paired(Flow::Empty, 0);
    assert_eq!((before, after), (0, 0));
    assert_eq!(log, vec![
        Update, Rebase(None), Apply(Change::None), Update, Archived(false),
        Update, Range(None, false), Bind(None), Notify,
    ]);
}

#[test]
fn paging_and_unchanged_revision_do_not_run_the_scan() {
    for (flow, flags) in [(Flow::Paging, 0), (Flow::Unchanged, 0), (Flow::Unchanged, 31)] {
        let (log, before, after) = paired(flow, flags);
        assert_eq!((before, after), (0, 0));
        assert!(log.iter().all(|c| !matches!(c, Call::Rebase(_) | Call::Exclude(_, _))));
    }
}

#[test]
fn independent_empty_codex_display_does_not_suppress_history_update() {
    let (log, before, after) = paired(Flow::EmptyCodex, 31);
    let (archive_log, _, _) = paired(Flow::Rewrite, 0);
    assert_eq!((before, after), (0, 0));
    assert_eq!(log, archive_log);
}
