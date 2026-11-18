use tiny_tally_offline_check::render;
fn main() {
    let samples = [
        ("normal", "Paper: 3\nInk: 2\nPaper: 4"),
        ("empty", "  \n"),
        ("ambiguous", "Salt: fine: 2"),
        ("error", "Paper: 2\nInk: many"),
        ("unicode", "東京: 3\nTea: 0"),
    ];
    for (name, src) in samples {
        println!("{name}\t{}", render(src));
    }
}
