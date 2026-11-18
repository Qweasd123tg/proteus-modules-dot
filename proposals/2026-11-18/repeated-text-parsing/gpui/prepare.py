"""Build source-bound, no-window before/after DOM stage: does not construct GPUI BlockNodes."""
from pathlib import Path
import sys, hashlib, shutil
here=Path(__file__).resolve().parent
src,wd=map(lambda s:Path(s).resolve(),sys.argv[1:3]); mode=sys.argv[3] if len(sys.argv)>3 else "normal"
fmt=Path("vendor/gpui-base/src/text/format")
for p in (fmt/"html.rs",fmt/"html5minify/mod.rs"):
    original=(src/p).read_bytes();expected={"html.rs":"a4586b249303cc4eca901cdfb593bd43f5f41283","mod.rs":"86fa5487380a1ebe808ba93d7117aa220b1eeda1"}[p.name];assert hashlib.sha1(b"blob "+str(len(original)).encode()+b"\0"+original).hexdigest()==expected
    (wd/p).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src/p,wd/p)
def emit(root,old):
    s=(root/fmt/"html.rs").read_text()
    mini=(root/fmt/"html5minify/mod.rs").read_text()
    start=s.index("fn cleanup_html(")
    if old:
        section=s[s.index("    let opts = ParseOpts {",s.index("pub(crate) fn parse(")):s.index("    let mut paragraph = HtmlParagraph::default();",s.index("pub(crate) fn parse("))]
        section=section[:section.rindex(".map_err(")].rstrip()+"\n"
        section=section.replace("    let dom = parse_document(","    parse_document(")
        m="pub fn dom(source: &str) -> std::io::Result<RcDom> {\n"+section+"}\n"+s[start:s.index("fn attr_value",start)]
    else:
        start=s.index("fn parse_dom(");m=s[start:s.index("fn attr_value",start)].replace("fn parse_dom(","pub fn dom(",1)
    if mode=="count":
        assert mini.count(".read_from(&mut r)?;")==1
        mini=mini.replace(".read_from(&mut r)?;",".read_from(&mut crate::Meter::new(&mut r))?;")
        if old:m=m.replace(".read_from(&mut cursor)",".read_from(&mut crate::Meter::new(&mut cursor))")
        else:m=m.replace(".read_from(&mut std::io::Cursor::new(bytes))",".read_from(&mut crate::Meter::new(std::io::Cursor::new(bytes)))")
    f=wd/"src"/("old_min.rs" if old else "new_min.rs");f.parent.mkdir(parents=True,exist_ok=True);f.write_text(mini)
    return '#[path="'+str(f)+'"] mod html5minify; pub mod measure { use html5ever::{ParseOpts,parse_document,tendril::TendrilSink}; use markup5ever_rcdom::RcDom;'+m+'}'
a=emit(src,True)
# Assemble only the isolated counterfactual function; do not patch the Desktop.
min_path=wd/fmt/"html5minify/mod.rs"
v=min_path.read_text()
s1="pub fn minify<R: io::Read>(&mut self, mut r: &mut R) -> io::Result<()> {"
v=v.replace(s1, """pub fn minify<R: io::Read>(&mut self, r: &mut R) -> io::Result<()> {
        self.minify_with_dom(r).map(drop)
    }
    pub(super) fn minify_with_dom<R: io::Read>(&mut self, mut r: &mut R) -> io::Result<RcDom> {""")
s2="self.minify_node(&None, &dom.document)"
assert s1 in (src/fmt/"html5minify/mod.rs").read_text() and v.count(s2)==1
min_path.write_text(v.replace(s2,s2+"?;\n    Ok(dom)"))
html_path=wd/fmt/"html.rs"
html_path.write_text((here/"after-stage.rs.inc").read_text()+"fn attr_value")
b=emit(wd,False)
(wd/"src"/"main.rs").write_text((here/"probe.rs.in").read_text().replace("BEFORE",a).replace("AFTER",b))
