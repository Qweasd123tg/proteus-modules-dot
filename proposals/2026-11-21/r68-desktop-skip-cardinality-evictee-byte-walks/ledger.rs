use crate::transcript::Entry;
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};

thread_local! { static RUN: RefCell<Option<Run>> = const { RefCell::new(None) }; }

#[derive(Default)]
struct Phase {
    visits: [usize; 3],
    nodes: [usize; 3],
    distinct: [BTreeSet<(u64, u8)>; 3],
}

struct Run {
    original: BTreeMap<u64, u8>,
    phases: BTreeMap<&'static str, Phase>,
    phase: &'static str,
    class: usize,
}

fn version(entry: &Entry) -> u8 {
    // Fixture versions are a single final ASCII marker, not payload hashes.
    entry
        .tool
        .as_ref()
        .and_then(|tool| tool.result.as_deref())
        .unwrap_or(&entry.text)
        .as_bytes()
        .last()
        .copied()
        .unwrap_or_default()
}

pub fn begin(entries: &[Entry]) {
    RUN.with(|cell| {
        assert!(cell.borrow().is_none());
        *cell.borrow_mut() = Some(Run {
            original: entries
                .iter()
                .map(|entry| (entry.key, version(entry)))
                .collect(),
            phases: BTreeMap::new(),
            phase: "outside",
            class: 0,
        });
    });
}

pub struct Restore(Option<&'static str>);
impl Drop for Restore {
    fn drop(&mut self) {
        RUN.with(|c| {
            if let Some(state) = c.borrow_mut().as_mut() {
                if let Some(old) = self.0 {
                    state.phase = old;
                }
            }
        });
    }
}

pub fn phase(label: &'static str) -> Restore {
    Restore(RUN.with(|cell| {
        cell.borrow_mut()
            .as_mut()
            .map(|state| std::mem::replace(&mut state.phase, label))
    }))
}

pub fn row(entry: &Entry) {
    RUN.with(|cell| {
        if let Some(run) = cell.borrow_mut().as_mut() {
            let version = version(entry);
            run.class = match run.original.get(&entry.key) {
                Some(&before) if before == version => 0, // unchanged resident
                Some(_) => 1,                            // changed resident
                None => 2,                               // newly loaded or inserted
            };
            let phase = run.phases.entry(run.phase).or_default();
            phase.visits[run.class] += 1;
            phase.distinct[run.class].insert((entry.key, version));
        }
    });
}

pub fn value() {
    RUN.with(|cell| {
        if let Some(run) = cell.borrow_mut().as_mut() {
            run.phases.entry(run.phase).or_default().nodes[run.class] += 1;
        }
    })
}

pub fn end(label: &str) {
    let mut r = RUN.with(|cell| cell.borrow_mut().take().unwrap());
    if r.phases.is_empty() {
        r.phases.insert("none", Phase::default());
    }
    for (phase, stats) in r.phases {
        println!(
            "work\t{label}\t{phase}\t{}\t{}\t{}",
            triple(stats.visits),
            triple(stats.distinct.map(|set| set.len())),
            triple(stats.nodes),
        );
    }
}
fn triple([a, b, c]: [usize; 3]) -> String {
    format!("{a},{b},{c}")
}
