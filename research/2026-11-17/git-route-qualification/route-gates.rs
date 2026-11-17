//! Opt-in public-geometry checks. Compile this file as a standalone test crate
//! with --extern placement pointing to the unchanged or candidate graph.rs library.
//! No Git repository, application, or network access is required by these tests.
extern crate placement;
use placement::{Row, Segment};
use std::collections::BTreeSet;

type Set = BTreeSet<usize>;
type History = Vec<Vec<usize>>;

fn render(h: &[Vec<usize>]) -> Vec<Row> {
    let ids = (0..h.len()).map(|i| i.to_string()).collect::<Vec<_>>();
    let input = h
        .iter()
        .enumerate()
        .map(|(i, p)| {
            (
                ids[i].as_str(),
                p.iter().map(|&j| ids[j].as_str()).collect(),
            )
        })
        .collect::<Vec<_>>();
    let rows = placement::layout(&input);
    assert_eq!(rows.len(), h.len());
    rows
}

// Later identically directed strokes with identical endpoints lie on top of
// earlier strokes in a half row. This doesn't rasterize curves or infer a
// connection at an interior crossing.
fn top(s: &[Segment]) -> Vec<Segment> {
    let mut occupied = BTreeSet::new();
    s.iter()
        .rev()
        .copied()
        .filter(|p| occupied.insert((p.from, p.to)))
        .collect()
}

fn parents(rows: &[Row], child: usize, straight_only: bool) -> Set {
    let r = &rows[child];
    let mut frontier = top(&r.down)
        .into_iter()
        .filter(|s| s.from == r.lane && (!straight_only || s.from == s.to))
        .map(|s| (s.to, s.color))
        .collect::<BTreeSet<_>>();
    let mut seen = Set::new();
    for (i, r) in rows.iter().enumerate().skip(child + 1) {
        if frontier.is_empty() {
            break;
        }
        let mut next = BTreeSet::new();
        let down = top(&r.down);
        for up in top(&r.up) {
            if !frontier.contains(&(up.from, up.color)) {
                continue;
            }
            if up.to == r.lane {
                seen.insert(i);
            } else {
                next.extend(
                    down.iter()
                        .filter(|s| s.from == up.to && s.color == up.color)
                        .map(|s| (s.to, s.color)),
                );
            }
        }
        frontier = next;
    }
    seen
}
fn check_all(h: &[Vec<usize>]) {
    let rows = render(h);
    for (i, p) in h.iter().enumerate() {
        assert_eq!(
            parents(&rows, i, false),
            p.iter().copied().collect::<Set>(),
            "row {i}"
        );
    }
}
// Open n unrelated tracks through the entire body, closing them only afterwards.
fn pinned(n: usize, body: &[Vec<usize>]) -> History {
    let mut h = (0..n)
        .map(|i| vec![2 * n + body.len() - 1 - i])
        .collect::<History>();
    h.extend(body.iter().map(|p| p.iter().map(|j| n + j).collect()));
    h.extend((0..n).map(|_| Vec::new()));
    h
}
#[test]
fn seven_commits_do_not_gain_parents() {
    check_all(&[
        vec![4],
        vec![4],
        vec![3, 6],
        vec![],
        vec![5, 6],
        vec![],
        vec![],
    ]);
}
#[test]
fn first_parent_stays_on_the_straight_exit_for_both_orders() {
    for order in [[2, 3], [3, 2]] {
        let h = [vec![2], order.to_vec(), vec![], vec![]];
        let rows = render(&h);
        assert_eq!(
            parents(&rows, 1, true),
            Set::from([order[0]]),
            "first parent of {order:?}"
        );
        check_all(&h);
    }
}
#[test]
fn paint_clean_61_plus_six_keeps_all_parents() {
    check_all(&pinned(
        61,
        &[
            vec![1, 2, 5],
            vec![2, 4],
            vec![3, 4],
            vec![],
            vec![],
            vec![],
        ],
    ));
}
#[test]
fn paint_clean_62_plus_six_keeps_all_parents() {
    check_all(&pinned(
        62,
        &[vec![2], vec![3, 5], vec![3], vec![4, 5], vec![], vec![]],
    ));
}
#[test]
fn paint_clean_62_plus_five_keeps_all_parents() {
    check_all(&pinned(
        62,
        &[vec![2], vec![2, 4], vec![3, 4], vec![], vec![]],
    ));
}
#[test]
fn paint_clean_61_plus_five_keeps_all_parents() {
    check_all(&pinned(
        61,
        &[vec![1, 2, 3], vec![2, 4], vec![3, 4], vec![], vec![]],
    ));
}

// A formerly dense page must not stretch the now-disconnected suffix.
// The width is derived from every physical endpoint; dot positions alone miss gaps.
fn width(rows: &[Row]) -> usize {
    rows.iter()
        .flat_map(|r| {
            std::iter::once(r.lane).chain(r.up.iter().chain(&r.down).flat_map(|s| [s.from, s.to]))
        })
        .max()
        .map_or(0, |i| i + 1)
}
#[test]
fn finished_frontier_does_not_stretch_a_late_shared_parent() {
    let n = 24;
    let q = 3 + 2 * n + 2;
    let own = q + 1;
    let common = q + 2;
    let late = q + 3;
    let mut tail = vec![vec![q]; 3];
    for i in 0..n {
        tail.push(vec![4 + 2 * i, common]);
        tail.push(vec![]);
    }
    tail.extend([
        vec![q - 1, late],
        vec![],
        vec![own, common, late],
        vec![],
        vec![],
        vec![],
    ]);
    let fresh = width(&render(&tail));
    let mut full = pinned(64, &[]); // 64 independent pairs, now completely closed.
    let start = full.len();
    full.extend(tail.iter().map(|p| p.iter().map(|j| start + j).collect()));
    let after = width(&render(&full)[start..]);
    assert_eq!(after, fresh, "closed-page prefix changed suffix width");
    assert!(
        after <= 6,
        "fixture budget: at most 6 tracks, observed {after}"
    );
}
#[test]
fn one_independent_branch_does_not_zigzag_as_neighbours_end() {
    let n = 8;
    let last = 3 + 2 * n;
    let mut h = vec![vec![2], vec![last], vec![]];
    for i in 0..n {
        h.push(vec![4 + 2 * i]);
        h.push(vec![]);
    }
    h.push(vec![]);
    let rows = render(&h);
    // This fixture has only two lanes; the other, repeatedly closed branch
    // has a different color. Compare geometry, not the chosen palette index.
    let color = rows[1].color;
    let bends = rows
        .iter()
        .flat_map(|r| r.up.iter().chain(&r.down))
        .filter(|s| s.color == color && s.from != s.to)
        .count();
    assert_eq!(
        bends, 0,
        "gratuitous sloped halves on one uninterrupted branch"
    );
}
