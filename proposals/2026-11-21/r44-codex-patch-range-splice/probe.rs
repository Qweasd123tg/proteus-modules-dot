use super::{apply_patch, patch};
use std::{fs, path::PathBuf, time::Instant};

#[test]
fn measure_apply_patch() {
    let root = PathBuf::from(std::env::var_os("CODEX_PATCH_FIXTURE").unwrap());
    let out = PathBuf::from(std::env::var_os("CODEX_PATCH_OUTPUT").unwrap());
    let tail = "untouched-line\n".repeat(48_000);
    for (label, removed, inserted, at_end) in [
        ("equal_head", 512, 512, false),
        ("shrink_head", 512, 32, false),
        ("grow_head", 32, 512, false),
        ("equal_tail", 512, 512, true),
        ("one_head", 1, 1, false),
    ] {
        let old: String = (0..removed).map(|i| format!("old-{i}\n")).collect();
        let new: String = (0..inserted).map(|i| format!("new-{i}\n")).collect();
        let position = |s: &str| {
            if at_end {
                format!("{tail}{s}")
            } else {
                format!("{s}{tail}")
            }
        };
        let hunk: String = old
            .lines()
            .map(|s| format!("-{s}\n"))
            .chain(new.lines().map(|s| format!("+{s}\n")))
            .collect();
        let input = patch(&format!(
            "*** Update File: f\n@@\n{}",
            hunk.trim_end_matches('\n')
        ));
        let file = root.join("f");
        fs::write(&file, position(&old)).unwrap();
        let start = Instant::now();
        let reply = apply_patch(&input, &root);
        let ns = start.elapsed().as_nanos();
        assert_eq!(
            reply.as_deref(),
            Ok("Success. Updated the following files:\nM f\n")
        );
        let after = fs::read(&file).unwrap();
        assert_eq!(after, position(&new).as_bytes(), "{label}");
        fs::write(out.join(label), after).unwrap();
        println!("R44 {label} {ns}");
    }
}

#[test]
fn differential_small_hunks() {
    use crate::{parser::UpdateFileChunk, update::contents};
    use std::io::{BufWriter, Write};
    let out = PathBuf::from(std::env::var_os("CODEX_PATCH_OUTPUT").unwrap());
    let mut wire = BufWriter::new(fs::File::create(out.join("small.jsonl")).unwrap());
    let mut chunks = Vec::new();
    for (old, new) in [
        (&[][..], &["x"][..]),
        (&[""][..], &[][..]),
        (&["b"][..], &[][..]),
        (&["a"][..], &["X", "Y"][..]),
        (&["a", "b"][..], &["X"][..]),
        (&["b", ""][..], &["B", ""][..]),
        (&["a", "a"][..], &[][..]),
    ] {
        for ctx in [None, Some("a")] {
            for eof in [false, true] {
                chunks.push(UpdateFileChunk {
                    change_context: ctx.map(str::to_string),
                    old_lines: old.iter().map(|s| (*s).into()).collect(),
                    new_lines: new.iter().map(|s| (*s).into()).collect(),
                    is_end_of_file: eof,
                    ..Default::default()
                });
            }
        }
    }
    let mut total = 0;
    for s in [
        "",
        "\n",
        "a\n",
        "a\na\n",
        "a\nb\n",
        "a\nb\n\n",
        "b\na\nb",
        "a\r\nb\r\n",
    ] {
        for first in &chunks {
            for second in &chunks {
                let result = contents(s, "f", &[first.clone(), second.clone()]);
                serde_json::to_writer(&mut wire, &result).unwrap();
                writeln!(wire).unwrap();
                total += 1;
            }
        }
    }
    wire.flush().unwrap();
    assert_eq!(total, 6272);
}
