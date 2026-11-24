#[path = "../src/inlines.rs"]
mod inlines;

use proteus_extension::{Value, ui};

#[test]
fn math_free_markdown_compiler_and_exact_caller() {
    let id = "r261-normal-prose";
    let source = "## Пример 🙂\n\n**жирное** / \"цитата\" &amp;\r\n\r\n- один\n- два";
    let html = markdown::to_html_with_options(source, &markdown::Options::gfm()).unwrap();
    assert!(!html.is_empty());
    assert_eq!(html.capacity(), html.len());
    let ptr = html.as_ptr();
    let direct = ui::rich_text(id, html);
    let actual = inlines::render(id, source, &["latex".to_owned()]).unwrap();
    let Value::String(owned) = &direct["html"] else {
        panic!("markdown html must be a string")
    };
    assert_eq!(owned.as_ptr(), ptr);
    assert_eq!(
        serde_json::to_vec(&actual).unwrap(),
        serde_json::to_vec(&direct).unwrap()
    );
    assert!(owned.contains("<strong>жирное</strong>"));
    assert_eq!(actual.as_object().unwrap().len(), 3);
    println!(
        "math-free native markdown HTML: {} tight UTF-8 bytes",
        owned.len()
    );
}
