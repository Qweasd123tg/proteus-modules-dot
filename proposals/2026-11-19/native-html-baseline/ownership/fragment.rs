use html5ever::{parse_document, tendril::TendrilSink};
use markup5ever_rcdom::{Handle, NodeData, RcDom};
#[allow(dead_code)]
mod stock;
use std::io::Cursor;

fn spans(html: &str) -> Vec<(String, bool)> {
    // Same two HTML5ever phases and options as format/html.rs::parse/cleanup_html.
    let mut bytes = Vec::new();
    let mut min = stock::Minifier::new(&mut bytes);
    min.omit_doctype(true);
    min.minify(&mut Cursor::new(html.as_bytes())).unwrap();
    let doc = parse_document(RcDom::default(), Default::default())
        .from_utf8().read_from(&mut Cursor::new(bytes)).unwrap();
    fn walk(node: &Handle, mut bold: bool, out: &mut Vec<(String, bool)>) {
        if let NodeData::Element { name, .. } = &node.data {
            bold |= matches!(name.local.as_ref(), "b" | "strong");
        }
        if let NodeData::Text { contents } = &node.data {
            out.push((contents.borrow().to_string(), bold));
        }
        for child in node.children.borrow().iter() {walk(child, bold, out);}
    }
    let mut out = vec![];
    walk(&doc.document, false, &mut out);
    out
}
fn main() {
    let (base,delta)=("<b>red", "plain");
    let mut split=spans(base); split.extend(spans(delta));
    let merged=spans(&format!("{base}{delta}"));
    println!("separate HTML fragments: {split:?}\nwhole HTML source: {merged:?}");
    assert_eq!(split, [("red".into(),true), ("plain".into(),false)]);
    assert_eq!(merged, [("redplain".into(),true)]);
}
