fn parse_dom(source: &str) -> std::io::Result<RcDom> {
    let (bytes, original) = cleanup_html(source);
    if let Some(dom) = original {
        return Ok(dom);
    }
    parse_document(RcDom::default(), ParseOpts::default())
        .from_utf8()
        .read_from(&mut std::io::Cursor::new(bytes))
}

fn cleanup_html(source: &str) -> (Vec<u8>, Option<RcDom>) {
    let mut bytes = Vec::new();
    let mut minifier = super::html5minify::Minifier::new(&mut bytes);
    minifier.omit_doctype(true);
    match minifier.minify_with_dom(&mut std::io::Cursor::new(source)) {
        // Both parsers use the same html5ever options. Only byte-identical input is reusable.
        Ok(dom) if bytes == source.as_bytes() => (bytes, Some(dom)),
        Ok(_) => (bytes, None),
        Err(_) => (source.as_bytes().to_vec(), None),
    }
}

