use std::sync::{Arc, Mutex};
// Exact BlockState, BlockSelection, methods and PartialEq from the pinned widget.
include!(env!("BLOCK_STATE_SOURCE"));
fn main() {
    let a = BlockState::default();
    let b = a.clone();
    let fresh = BlockState::default();
    a.set_selection(Some(BlockSelection::Full));
    assert!(b.is_selected());
    assert!(!fresh.is_selected());
    assert!(a == fresh); // AST equality intentionally ignores runtime selection.
    b.clear_selection();
    assert!(!a.has_selection_observation());
    println!("set A full: clone B sees full, independent C sees none; A == C; clear B: A sees none.");
}
