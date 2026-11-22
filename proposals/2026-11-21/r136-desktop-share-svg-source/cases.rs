use super::*;
use crate::counter::measure;
use crate::declarative::protocol::{self, Incoming};
use crate::{DevicePixels, fingerprint, size};
use serde_json::{Value, json};

include!("mode.inc.rs");

const NS: &str = "http://www.w3.org/2000/svg";

fn diagram(name: &str, n: usize) -> String {
    let mut text = format!(
        r##"<svg xmlns="{NS}" viewBox="0 0 120 80"><title>Схема 日本語 🧩 {name}</title><defs><path id="flow" d="M0 0L120 80"/></defs><use href="#flow"/>"##
    );
    for index in 0..n {
        text.push_str(&format!(
            r##"<rect x="{}" y="{}" width="3" height="2" fill="#1a3445"/>"##,
            index % 120,
            index % 80
        ));
    }
    text.push_str("</svg>");
    text
}
fn wire_value(source: &str, w: u32, h: u32) -> Value {
    json!({"type":"view", "view":"content:synthetic", "sequence":17,"source_revision":3,
      "root":{"type":"svg","source":source,"width":w,"height":h}})
}
fn decode(line: &str) -> Node {
    let Incoming::View {
        root,
        sequence: 17,
        source_revision: Some(3),
        ..
    } = protocol::parse(line).unwrap()
    else {
        panic!("valid SVG view")
    };
    root
}
fn owned(source: String, w: f32, h: f32) -> Node {
    Node::Svg {
        source: source.into(),
        width: w,
        height: h,
        baseline: None,
        em_size: None,
    }
}
fn text(node: &Node) -> &str {
    let Node::Svg { source, .. } = node else {
        panic!("a single SVG required")
    };
    source
}
fn key_text(key: &Key) -> &str {
    &key.source
}
fn parsed_text<'a>(images: &'a Images, source: &str) -> Option<&'a str> {
    images
        .parsed
        .get_key_value(source)
        .map(|(key, _)| -> &str { key })
}
fn same_storage(a: &str, b: &str) -> bool {
    assert_eq!(a, b);
    a.as_ptr() == b.as_ptr()
}
fn trace(label: &str, row: Value) {
    eprintln!("TRACE {label} {row}");
}
fn work(label: &str, len: usize, row: [isize; 3]) {
    eprintln!("WORK {label} {}", json!([len, row[0], row[1], row[2]]));
}

#[test]
fn actual_serde_protocol_and_svg_validator() {
    eprintln!("ARM {}", env!("R136_ARM"));
    let source = diagram("wire", 4);
    let line = wire_value(&source, 120, 80).to_string();
    let escaped = line.replace("С", r"\u0421").replace("🧩", r"\ud83e\udde9");
    let plain = decode(&line);
    let escaped = decode(&escaped);
    assert_eq!(text(&plain), source);
    assert_eq!(plain, escaped);
    let preformat = format!("{plain:?}");
    assert_eq!(preformat, format!("{escaped:?}"));
    assert!(!same_storage(text(&plain), text(&escaped)));
    let mut rows = vec![];
    for (label, svg, width, hint) in [
        ("malformed", "<svg", 120, ""),
        ("wrong-root", "<document/>", 120, "svg root element"),
        ("width", "<svg/>", 0, "dimensions"),
        (
            "empty-foreign-tag",
            "<svg><foreignObject/></svg>",
            120,
            "not html or scripts",
        ),
        (
            "nonfragment-token",
            "<svg><use href=\"fixture-reference\"/></svg>",
            120,
            "local #fragments",
        ),
    ] {
        let mut message = wire_value(svg, width, 80);
        let result = protocol::parse(&message.to_string()).unwrap();
        let Incoming::ContentError {
            error,
            view,
            sequence,
            source_revision,
            session_dir,
        } = result
        else {
            panic!("unexpected accepted envelope: {label}")
        };
        assert_eq!(view, "content:synthetic");
        assert_eq!(
            (sequence, source_revision, session_dir),
            (17, Some(3), None)
        );
        assert!(error.to_lowercase().contains(hint), "{label}: {error}");
        message["view"] = json!("document:synthetic");
        let err = protocol::parse(&message.to_string())
            .unwrap_err()
            .to_string();
        assert!(err.to_lowercase().contains(hint), "{label}: {err}");
        rows.push(json!([label, error, err]));
    }
    let near_cap = format!("<svg><!--{}--></svg>", "x".repeat(1024 * 1024 - 18));
    assert_eq!(near_cap.len(), 1024 * 1024);
    assert_eq!(
        text(&decode(&wire_value(&near_cap, 4096, 4096).to_string())).len(),
        near_cap.len()
    );
    let over = format!("<svg><!--{}--></svg>", "x".repeat(1024 * 1024 - 17));
    assert!(
        matches!(protocol::parse(&wire_value(&over,1,1).to_string()).unwrap(),
        Incoming::ContentError{error,..} if error=="svg source exceeds 1 MiB")
    );
    for value in [
        Value::Null,
        json!(14),
        json!(["text"]),
        json!({"raw":"<svg/>"}),
    ] {
        let mut v = wire_value(&source, 120, 80);
        v["root"]["source"] = value;
        let invalid = protocol::parse(&v.to_string()).unwrap_err().to_string();
        assert!(invalid.contains("a string"));
        rows.push(json!(invalid));
    }
    let mut extra = wire_value(&source, 120, 80);
    extra["root"]["unexpected"] = json!(true);
    assert!(
        protocol::parse(&extra.to_string())
            .unwrap_err()
            .to_string()
            .contains("unknown field")
    );
    trace(
        "serde-validator",
        json!([
            rows,
            preformat,
            fingerprint(source.as_bytes()),
            near_cap.len()
        ]),
    );
}

#[test]
fn first_prepared_source_keeps_exactly_one_backing_and_quantifies_cost() {
    let source = diagram("ordinary-medium", 768);
    assert!((32000..64000).contains(&source.len()));
    let wire = wire_value(&source, 120, 80).to_string();
    let source_len = source.len();
    let renderer = SvgRenderer::default();
    RASTERS.with(|cache| assert_eq!(cache.borrow().usage(), (0, 0, 0)));
    let (root, decode_work) = measure(|| decode(&wire));
    let owned_before = text(&root).as_ptr();
    assert_eq!(text(&root), source);
    let mut images = Images::default();
    let (_, prepare_work) = measure(|| images.prepare_with(&root, &renderer));
    images.rasterize_with(&root, 1.);
    let parsed = parsed_text(&images, &source).unwrap();
    assert_eq!(same_storage(text(&root), parsed), SHARED);
    let own_key = images.key(&source, 120., 80.).unwrap();
    assert!(same_storage(parsed, key_text(&own_key)));
    assert_eq!(renderer.parsed.get(), 1);
    assert_eq!(renderer.painted.get(), 0);
    assert!(images.error().is_none());
    let borrowed = images.get(&source, 120., 80.).unwrap();
    // Preparation and offscreen request allocate no bitmap.
    RASTERS.with(|cache| assert_eq!(cache.borrow().usage(), (0, 0, 0)));
    assert_eq!(text(&root).as_ptr(), owned_before);
    assert_eq!(key_text(&own_key).len(), source_len);
    drop(own_key);
    drop(borrowed);
    let ((), dropped_root) = measure(|| drop(root));
    assert_eq!(parsed_text(&images, &source).unwrap(), source);
    let ((), dropped_images) = measure(|| drop(images));
    assert!(dropped_root[2] <= 0 && dropped_images[2] < 0);
    let mut refusal = Images::default();
    let refuse = wire_value(&diagram("fixture-refuse-parse", 4), 120, 80).to_string();
    let bad = decode(&refuse);
    let (_, refused) = measure(|| refusal.prepare_with(&bad, &renderer));
    assert_eq!(refusal.error().as_deref(), Some("SVG: inert parse refusal"));
    assert!(refusal.parsed.is_empty() && refusal.get(text(&bad), 120., 80.).is_none());
    let tiny = wire_value("<svg/>", 1, 1).to_string();
    let (tiny_root, tiny_decode) = measure(|| decode(&tiny));
    let mut tiny_images = Images::default();
    let (_, tiny_prepare) = measure(|| tiny_images.prepare_with(&tiny_root, &renderer));
    assert!(tiny_images.error().is_none());
    work("decode-tiny", text(&tiny_root).len(), tiny_decode);
    work("prepare-tiny", text(&tiny_root).len(), tiny_prepare);
    let ((replacement, same_images), equal_receipt) = measure(|| {
        let before = decode(&wire);
        let mut equal_images = Images::default();
        equal_images.prepare_with(&before, &renderer);
        let next = decode(&wire);
        equal_images.prepare_with(&next, &renderer);
        drop(before);
        (next, equal_images)
    });
    assert!(!same_storage(
        text(&replacement),
        parsed_text(&same_images, &source).unwrap()
    ));
    work("equal-redecode-live", source_len, equal_receipt);
    work("decode-live", source_len, decode_work);
    work("prepare-live", source_len, prepare_work);
    work("drop-root", source_len, dropped_root);
    work("drop-images", source_len, dropped_images);
    work("renderer-refusal", text(&bad).len(), refused);
    trace(
        "first-prepare",
        json!([
            source_len,
            fingerprint(source.as_bytes()),
            renderer.parsed.get(),
            renderer.painted.get()
        ]),
    );
}

#[test]
fn textual_equality_lookup_different_source_and_budget_exact() {
    let renderer = SvgRenderer::default();
    let a = diagram("similar-a", 17);
    let b = diagram("similar-b", 17);
    assert_eq!(a.len(), b.len());
    let one = decode(&wire_value(&a, 640, 360).to_string());
    let equal = decode(&wire_value(&a, 640, 360).to_string());
    let two = decode(&wire_value(&b, 640, 360).to_string());
    assert_eq!(one, equal);
    assert_ne!(one, two);
    assert!(!same_storage(text(&one), text(&equal)));
    let mut images = Images::default();
    images.prepare_with(&one, &renderer);
    images.rasterize_with(&one, 1.);
    let old_ptr = parsed_text(&images, &a).unwrap().as_ptr();
    let item = images.get(text(&one), 640., 360.).unwrap();
    let bitmap = item.resolve(&renderer, None).unwrap();
    let dpi1 = bitmap.0.0;
    assert_eq!(dpi1, size(DevicePixels(540), DevicePixels(360)));
    assert_eq!(bitmap.0.1, fingerprint(a.as_bytes()));
    let existing = RASTERS.with(|cache| cache.borrow().usage());
    assert_eq!(existing, (1, 540 * 360, a.len()));
    images.prepare_with(&equal, &renderer);
    assert_eq!(renderer.parsed.get(), 1);
    assert_eq!(parsed_text(&images, &a).unwrap().as_ptr(), old_ptr);
    assert!(!same_storage(
        parsed_text(&images, &a).unwrap(),
        text(&equal)
    ));
    assert!(Arc::ptr_eq(
        &bitmap,
        &images
            .get(text(&equal), 640., 360.)
            .unwrap()
            .resolve(&renderer, None)
            .unwrap()
    ));

    // Width/height and source changes still make old owner leases stale.
    images.rasterize_with(&equal, 2.);
    assert!(item.resolve(&renderer, None).is_none());
    let dpi2 = images
        .get(&a, 640., 360.)
        .unwrap()
        .resolve(&renderer, None)
        .unwrap()
        .0
        .0;
    assert_eq!(dpi2, size(DevicePixels(1080), DevicePixels(720)));
    images.prepare_with(&two, &renderer);
    assert_eq!(renderer.parsed.get(), 2);
    assert!(images.get(&a, 640., 360.).is_none());
    let other = images
        .get(&b, 640., 360.)
        .unwrap()
        .resolve(&renderer, None)
        .unwrap();
    assert_eq!(other.0.1, fingerprint(b.as_bytes()));
    assert_eq!(renderer.painted.get(), 3);
    trace(
        "textual-key-dpi",
        json!([
            renderer.parsed.get(),
            renderer.painted.get(),
            [dpi1.width.0, dpi1.height.0],
            [dpi2.width.0, dpi2.height.0],
            existing,
            fingerprint(a.as_bytes()),
            fingerprint(b.as_bytes())
        ]),
    );
}

#[test]
fn raster_refusal_expired_owners_and_moved_string() {
    let mut source = diagram("retained-owner", 2);
    source.shrink_to_fit();
    let source_ptr = source.as_ptr();
    let root = owned(source, 15., 10.);
    assert_eq!(text(&root).as_ptr(), source_ptr);
    let renderer = SvgRenderer::default();
    let mut first = Images::default();
    let mut second = Images::default();
    first.prepare_with(&root, &renderer);
    second.prepare_with(&root, &renderer);
    first.rasterize_with(&root, 1.);
    second.rasterize_with(&root, 1.);
    let r1 = first.get(text(&root), 15., 10.).unwrap();
    let r2 = second.get(text(&root), 15., 10.).unwrap();
    let b = r1.resolve(&renderer, None).unwrap();
    assert!(Arc::ptr_eq(&b, &r2.resolve(&renderer, None).unwrap()));
    assert_eq!(second.parsed.get_key_value(text(&root)).is_some(), true);
    let fail = first.get(text(&root), 7., 7.).unwrap();
    assert!(fail.resolve(&renderer, None).is_none());
    assert_eq!(first.error().as_deref(), Some("SVG: inert raster refusal"));
    assert!(first.get(text(&root), 7., 7.).is_none());
    let kept = text(&root).to_owned();
    drop(root);
    drop(first);
    assert!(r1.resolve(&renderer, None).is_none());
    assert!(r2.resolve(&renderer, None).is_some());
    assert_eq!(parsed_text(&second, &kept).unwrap(), kept);
    drop(second);
    assert!(r2.resolve(&renderer, None).is_none());
    let remaining = RASTERS.with(|cache| cache.borrow().usage());
    assert_eq!(remaining, (0, 0, 0));
    trace(
        "lease-expiry",
        json!([
            renderer.parsed.get(),
            renderer.painted.get(),
            remaining,
            b.0.1,
            kept.len()
        ]),
    );
}
