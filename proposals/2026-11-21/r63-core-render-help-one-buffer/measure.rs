mod implementations;
mod test_alloc;

use implementations::{BUILTINS, candidate, stock};
use proteus_contracts::app_protocol::commands::{CommandKind, UserCommand};
use std::{hint::black_box, io::Write as _};

fn command(name: &str, args: &str, description: &str, kind: CommandKind) -> UserCommand {
    UserCommand {
        name: name.into(),
        arguments: args.into(),
        description: description.into(),
        kind,
        source: match kind {
            CommandKind::Service => "host",
            CommandKind::Tool => "tool:demo",
            CommandKind::Prompt => "profile",
        }
        .into(),
    }
}

fn builtins() -> Vec<UserCommand> {
    let mut result: Vec<_> = BUILTINS
        .iter()
        .map(|(name, description, args)| command(name, args, description, CommandKind::Service))
        .collect();
    result.sort_by(|a, b| a.name.cmp(&b.name));
    result
}

fn mixed() -> Vec<UserCommand> {
    let mut result = builtins();
    result.push(command(
        "probe",
        "[ARGUMENTS]",
        "Run a demo",
        CommandKind::Tool,
    ));
    result.push(command(
        "review",
        "[ARGUMENTS]",
        "Review a target",
        CommandKind::Prompt,
    ));
    result.sort_by(|a, b| a.name.cmp(&b.name));
    result
}

#[test]
fn places_exact_separators_and_preserves_input_order() {
    let fixture = [
        command("z", "", "ru 😀\r\nnext", CommandKind::Prompt),
        command("a", " <- — → >\0", "", CommandKind::Tool),
    ];
    assert_eq!(
        candidate(&fixture),
        "/z  — ru 😀\r\nnext\n/a  <- — → >\0 — "
    );
    assert_eq!(candidate(&[]), "");
    let last_newline = [command("line", "", "text\n", CommandKind::Service)];
    assert_eq!(candidate(&last_newline), "/line  — text\n");
}

fn make_catalog(seed: usize, count: usize) -> Vec<UserCommand> {
    let names = [
        "zero",
        "next",
        "command-with-hyphen",
        "",
        "имя😀",
        " another ",
    ];
    let args = ["", "[ARGS]", "\nline", " — ", "x\0y", "☃"];
    let descriptions = [
        "plain",
        "",
        "Японский 語",
        "multiple\r\nlines\n",
        "\t   \0",
        " — ",
    ];
    (0..count)
        .map(|i| {
            let kind =
                [CommandKind::Service, CommandKind::Tool, CommandKind::Prompt][(i + seed) % 3];
            command(
                names[(seed + i) % names.len()],
                args[(seed / 2 + i * 5) % args.len()],
                descriptions[(seed / 3 + i * 7) % descriptions.len()],
                kind,
            )
        })
        .collect()
}

#[test]
fn catalog_rendering_matches_exact_prior_arm_byte_for_byte() {
    let output = std::fs::File::create(std::env::var_os("R63_SNAPSHOT").unwrap()).unwrap();
    let mut out = std::io::BufWriter::new(output);
    let long_help = vec![command(
        "long",
        "[VALUE]",
        &"語😀".repeat(4096),
        CommandKind::Prompt,
    )];
    let fixtures = [vec![], builtins(), mixed(), long_help];
    let generated = (0..128).flat_map(|i| [1, 3, 9, 32].map(move |n| make_catalog(i, n)));
    let mut count = 0;
    for (fixture, catalog) in fixtures.into_iter().chain(generated).enumerate() {
        let prior = stock(&catalog);
        let next = candidate(&catalog);
        assert_eq!(prior.as_bytes(), next.as_bytes(), "fixture {fixture}");
        assert_eq!(next.capacity(), next.len(), "fixture {fixture}");
        out.write_all(&(next.len() as u64).to_le_bytes()).unwrap();
        out.write_all(next.as_bytes()).unwrap();
        count += 1;
    }
    out.flush().unwrap();
    assert_eq!(count, 516);
    println!("{count} byte-identical help outputs");
}

#[test]
fn one_sized_allocation_for_nonempty_catalogs() {
    for (name, catalog) in [
        ("empty", vec![]),
        ("builtins-8", builtins()),
        ("mixed-10", mixed()),
        ("64-extra-entries", make_catalog(7, 64)),
        (
            "long-argument-and-description",
            vec![command(
                "long",
                &"value".repeat(2048),
                &"話😀".repeat(4096),
                CommandKind::Tool,
            )],
        ),
    ] {
        let (expected, old) = test_alloc::measure(|| black_box(stock(black_box(&catalog))));
        let (actual, new) = test_alloc::measure(|| black_box(candidate(black_box(&catalog))));
        assert_eq!(expected, actual);
        assert_eq!(new.calls, usize::from(!catalog.is_empty()));
        assert_eq!(new.bytes, actual.len());
        if !catalog.is_empty() {
            assert!(new.calls < old.calls && new.bytes < old.bytes, "{name}");
        }
        println!(
            "{name:29} {:2} lines; requests {:3} -> {:3}; bytes {:7} -> {:7}; exact output {}",
            catalog.len(),
            old.calls,
            new.calls,
            old.bytes,
            new.bytes,
            actual.len()
        );
    }
}
