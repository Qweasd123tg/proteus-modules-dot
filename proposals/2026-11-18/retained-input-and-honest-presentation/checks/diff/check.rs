use proteus_diff::{FileInfo, Kind, Pair, parse};
const NONE: &str = "Текст изменений не предоставлен";
const ADD: &str = "diff --git a/empty.txt b/empty.txt\nnew file mode 100644\n";
const DELETE: &str = "diff --git a/gone b/gone\ndeleted file mode 100644\n";
const RENAME: &str =
    "diff --git a/old b/new\nsimilarity index 100%\nrename from old\nrename to new\n";
const EDIT: &str = "--- a/data.csv\n+++ b/data.csv\n@@ -1 +1 @@\n-old value\n+new value\n";
fn info(path: &str, status: &str, message: Option<&str>) -> FileInfo {
    FileInfo {
        path: path.into(),
        status: status.into(),
        message: message.map(Into::into),
    }
}
fn main() {
    let statuses = [
        "added",
        "untracked",
        "modified",
        "renamed",
        "conflict",
        "",
        "copied",
    ];
    let (mut neutral, mut controls) = (0, 0);
    for prefix in ["", EDIT, ADD, DELETE, RENAME] {
        for status in statuses {
            let before = parse(prefix, &[]);
            let files = parse(prefix, &[info("другая.tsv", status, None)]);
            let (card, unchanged) = files.split_last().unwrap();
            assert_eq!(unchanged, before);
            assert_eq!(card.status, status);
            assert_eq!(card.path, "другая.tsv");
            assert!(card.patch.is_empty());
            assert_eq!((card.added, card.removed), (0, 0));
            assert_eq!(card.pairs, [Pair::Full(0)]);
            assert_eq!(card.unified, [0]);
            assert_eq!(card.lines.len(), 1);
            assert_eq!(card.lines[0].kind, Kind::Note);
            neutral += usize::from(card.lines[0].text == NONE);
        }
    }
    for (raw, expected) in [
        (ADD, "Пустой файл"),
        (DELETE, "Файл удалён"),
        (RENAME, "Файл переименован без изменения содержимого"),
    ] {
        let f = parse(raw, &[]);
        assert_eq!(f[0].lines[0].text, expected);
        assert_eq!(f[0].patch, raw);
        controls += 1;
    }
    for status in statuses.into_iter().chain(["deleted"]) {
        for m in ["Too large", "Двоичный файл", "No text available"] {
            for metadata in [
                vec![info("data", status, Some(m))],
                vec![info("data", status, None), info("data", status, Some(m))],
            ] {
                let f = parse("", &metadata);
                assert_eq!(f.len(), 1);
                assert_eq!(f[0].lines[0].text, m);
                controls += 1;
            }
        }
    }
    assert_eq!(
        parse("", &[info("gone", "deleted", None)])[0].lines[0].text,
        "Файл удалён"
    );
    controls += 1;
    let f = parse(
        EDIT,
        &[info("data.csv", "modified", Some("provider summary"))],
    );
    assert_eq!(f.len(), 1);
    assert_eq!(f[0].patch, EDIT);
    assert_eq!((f[0].added, f[0].removed), (1, 1));
    assert_eq!(f[0].lines[1].text, "old value");
    assert_eq!(f[0].lines[2].text, "new value");
    controls += 1;
    assert!(parse("", &[]).is_empty());
    controls += 1;
    println!(
        "Metadata-only no-message cards without invented contents: {neutral}/35; structural controls passed in all 35.\nUnchanged existing controls: {controls}/{controls}."
    );
    if neutral != 35 {
        std::process::exit(1);
    }
}
