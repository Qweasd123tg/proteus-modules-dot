#!/usr/bin/env python3
"""Verify exact plaintext escape patch and both #544 application orders offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

PATH = "packages/markdown-render/src/plain.rs"
PINS = {
    "stock": ("37a30ecd9f65c8115dc82bb1f6c58ff4d31947e6",
              "a0120188e6637cb93b222d1e3fe0c54626c068a155a95a6017aacc07d92d8494"),
    "candidate": ("f572a4b15fdd455ecf352ed69e82fb5daad3c173",
                  "4d74604dadc495afb2782fc1f4a820d038f755ee3a27e52545fdd491ca4b4091"),
    "prior_product": ("167f6524452ee998c26893e2a8cab2ffa932c76a",
                      "8fe60d65fd30ca022af4e5220879174772866f2067996364cc4006f4170bb1c4"),
    "both": ("739634ee4ffb0c5998c2669e8b15352bb285c637",
             "f201c03aa392cc28fc93366428776075b53c1376549c9c7ce481199aa117ffbc"),
    "patch": ("47dfcbf4f869aedbcc98ac550c8acc47c3f62181",
              "3e39aab5ebb1a54bd1067e38acb42efed7d7ac3e9242b7c6246c3a29ea5f7702"),
    "prior": ("104040cc8ddbb68c068bbccb181f371a5bc68fd7",
              "2a7147cc3838573266f76c718c81d12ba366c22c73f27104e48d270f69605095"),
    "dispatch": ("488263bf5ffc17091c043e91a4ad613047172340",
                 "9e6fbaf99e28ef0a33069b66999ac77f3e8642b8cbab2eb3cf36d49a07e681d8"),
}
RUSTC_VERSION = "rustc 1.95.0 (59807616e 2026-04-14)"
RUSTC_SHA = "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6"


def check(condition, label):
    if not condition:
        raise ValueError(label)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def identity(tag, data):
    git, digest = PINS[tag]
    check(sha(data) == digest and hashlib.sha1(
        f"blob {len(data)}\0".encode() + data).hexdigest() == git, f"identity: {tag}")


def apply(raw, patch, before, after, shift=0, reverse=False):
    header = (f"diff --git a/{PATH} b/{PATH}\n"
              f"index {PINS[before][0]}..{PINS[after][0]} 100644\n"
              f"--- a/{PATH}\n+++ b/{PATH}\n").encode()
    check(patch.startswith(header), "expected single-file Git patch")
    hunk = patch[len(header):].splitlines(keepends=True)
    m = re.fullmatch(rb"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n", hunk[0])
    check(m is not None and all(line[:1] in (b" ", b"+", b"-") for line in hunk[1:]),
          "single exact hunk")
    begin, count, end, new_count = map(int, m.groups())
    old, new = ([line[1:] for line in hunk[1:] if line[:1] != skip] for skip in (b"+", b"-"))
    check((len(old), len(new)) == (count, new_count) and begin == end, "exact hunk coordinates")
    if reverse:
        old, new = new, old
    lines = raw.splitlines(keepends=True)
    at = begin - 1 + shift
    check(lines[at:at+len(old)] == old, "exact hunk context, no context dropping")
    return b"".join(lines[:at] + new + lines[at+len(old):])


def compose(base, patch, prior):
    step = lambda src, inv=False, shift=0: apply(src, patch, "stock", "candidate", shift, inv)
    pr544 = lambda src, inv=False: apply(src, prior, "stock", "prior_product", reverse=inv)
    candidate, prior_product = step(base), pr544(base)
    identity("candidate", candidate)
    identity("prior_product", prior_product)
    check(candidate[:candidate.index(b"fn escape(")] == base[:base.index(b"fn escape(")],
          "all recognition / render / collection bytes unchanged")
    check(candidate[candidate.index(b"#[cfg(test)]"):] == base[base.index(b"#[cfg(test)]"):],
          "full native package tests unchanged")
    shift = prior_product[:prior_product.index(b"fn escape(")].count(b"\n") - \
        base[:base.index(b"fn escape(")].count(b"\n")
    check(shift == 2, "#544 adds exactly two preceding lines")
    both = step(prior_product, shift=shift)
    identity("both", both)
    check(pr544(candidate) == both, "both application orders")
    check(step(candidate, inv=True) == pr544(prior_product, inv=True) == base,
          "standalone exact reversals")
    check(step(both, inv=True, shift=shift) == prior_product and pr544(both, inv=True) == candidate,
          "both exact rollback paths")
    return dict(stock=base, candidate=candidate, prior_product=prior_product, both=both)


def lift(name, raw):
    s = raw.decode()
    body = s[s.index("pub(super) fn render("):s.index("#[cfg(test)]")]
    escape = body[body.index("fn escape("):]
    check(escape.count("output: &mut String") == 1, "instrumented auxiliary lift")
    instrumented = escape.replace("fn escape(", "pub(super) fn observe(", 1).replace(
        "output: &mut String", "output: &mut Trace", 1)
    return (f"mod {name} {{\n"
            "use super::{markdown::{self, Constructs, ParseOptions, mdast::Node}, Result, Trace, Value, ui};\n"
            "use std::ops::Range;\n"
            + body.replace("fn escape(", "pub(super) fn escape(", 1) + instrumented + "}\n")


def constructs(raw):
    body = raw.decode().split("let constructs = Constructs {\n", 1)[1].split("    };", 1)[0]
    pairs = re.findall(r"^        (\w+): (true|false),$", body, re.M)
    check(len(pairs) == len(body.splitlines()) and len(pairs) == 34
          and [key for key, val in pairs if val == "true"] == ["gfm_autolink_literal"],
          "exact parser construct declarations")
    fields = "\n".join(f"pub {key}: bool," for key, _ in pairs)
    assertion = " && ".join(f"q.constructs.{key}" if val == "true" else f"!q.constructs.{key}"
                            for key, val in pairs)
    return STUB.replace("/*FIELDS*/", fields).replace("/*VERIFY*/", assertion)


STUB = r'''
type Result<T> = std::result::Result<T, String>;
#[derive(Debug, PartialEq, Eq)]
struct Value { id: String, html: String }
macro_rules! anyhow {
    ($fmt:literal) => { format!($fmt) };
}
mod ui {
    use super::Value;
    pub fn rich_text(id: &str, html: String) -> Value {
        Value {id:id.into(), html}
    }
}
mod markdown {
    use std::cell::RefCell;
    #[derive(Default)]
    pub struct Constructs { /*FIELDS*/ }
    #[derive(Default)]
    pub struct ParseOptions { pub constructs: Constructs, pub placeholder: bool }
    pub mod mdast {
        pub struct Point { pub offset: usize }
        pub struct Position { pub start: Point, pub end: Point }
        pub struct Link { pub position: Option<Position>, pub nested: Vec<Node> }
        pub enum Node { Link(Link), Branch(Vec<Node>), Leaf }
        impl Node {
            pub fn children(&self) -> Option<&[Node]> {
                match self {
                    Self::Branch(children) => Some(children),
                    Self::Link(link) => Some(&link.nested),
                    Self::Leaf => None,
                }
            }
        }
    }
    type Parsed = super::Result<mdast::Node>;
    thread_local! { static REPLY: RefCell<Option<Parsed>> = const { RefCell::new(None) }; }
    pub fn set(value: Parsed) { REPLY.with_borrow_mut(|p| assert!(p.replace(value).is_none())); }
    pub fn drained() { REPLY.with_borrow(|p| assert!(p.is_none())); }
    pub fn to_mdast(_: &str, q: &ParseOptions) -> Parsed {
        assert!(!q.placeholder && /*VERIFY*/);
        REPLY.with_borrow_mut(|p| p.take().expect("unexpected Markdown parser call"))
    }
}
#[derive(Default)]
struct Trace { text: String, scalar: usize, spans: usize }
impl Trace {
    fn push(&mut self, c: char) { self.scalar += 1; self.text.push(c); }
    fn push_str(&mut self, s: &str) {
        assert!(!s.is_empty());
        self.spans += 1; self.text.push_str(s);
    }
}
'''


TESTS = r'''
use markdown::mdast::{Link, Node, Point, Position};
type Escape = fn(&str, &mut String);
type Render = fn(&str, &str) -> Result<Value>;
const ESCAPES: [Escape;4] = [stock::escape,candidate::escape,prior_product::escape,both::escape];
const RENDERS: [Render;4] = [stock::render,candidate::render,prior_product::render,both::render];

fn escaped(f: Escape, source: &str) -> String {
    // Production already has a prefix; keep it unchanged, including its Unicode.
    let mut out = String::from("prefix🦀|");
    f(source, &mut out);
    out
}
fn same_escape(source: &str) {
    let gold = escaped(ESCAPES[0],source);
    for f in &ESCAPES[1..] { assert_eq!(escaped(*f,source).as_bytes(),gold.as_bytes()); }
}
fn node(range: Option<(usize,usize)>, nested: Vec<Node>) -> Node {
    let position = range.map(|(start,end)| Position{start:Point{offset:start},end:Point{offset:end}});
    Node::Link(Link{position,nested})
}
fn links(s: &str, tokens: &[&str]) -> Node {
    let mut cursor = 0;
    let mut nodes = Vec::new();
    for tok in tokens {
        let start = cursor+s[cursor..].find(tok).unwrap();
        cursor = start+tok.len();
        nodes.push(node(Some((start,cursor)),vec![]));
    }
    Node::Branch(vec![Node::Leaf,Node::Branch(nodes)])
}
fn rendered(s: &str, setup: impl Fn() -> Option<Result<Node>>) -> Result<Value> {
    let rr = |render: Render| {
        if let Some(p) = setup() { markdown::set(p); }
        let result = render("plain-id🧪",s);
        markdown::drained();
        result
    };
    let gold = rr(RENDERS[0]);
    for f in &RENDERS[1..] { assert_eq!(rr(*f),gold); }
    gold
}

#[test]
fn exact_entities_order_quotes_and_controls() {
    for f in ESCAPES {
        assert_eq!(escaped(f,"α&<>\"'&amp;\0\r\n\t😀e\u{0301}\u{fffd}"),
                   "prefix🦀|α&amp;&lt;&gt;&quot;'&amp;amp;\0\r\n\t😀e\u{0301}\u{fffd}");
        assert_eq!(escaped(f,""),"prefix🦀|");
        assert_eq!(escaped(f,"  "),"prefix🦀|  ");
    }
}
#[test]
fn every_unicode_scalar_and_boundaries() {
    let all: String = (0..=0x10ffff).filter_map(char::from_u32).collect();
    same_escape(&all);
    same_escape(&format!("&{all}\""));
    same_escape(&format!("界<\"&>😀\u{10ffff}"));
    for b in 0..=127_u8 { same_escape(&format!("é{}\"😀",b as char)); }
}
#[test]
fn generated_escape_and_render_pairs() {
    let atoms = ["","&","<",">","\"","😀","e\u{0301}","\r\n", "'", "👩🏽‍🔬", "β", "\0", "&lt;", "literal"];
    let mut state = 987654_u64;
    for i in 0..4096 {
        let mut s = String::new();
        for _ in 0..(i%97) {
            state=state.wrapping_mul(6364136223846793005).wrapping_add(1);
            s.push_str(atoms[((state>>32) as usize)%atoms.len()]);
        }
        same_escape(&s);
        if i%3 == 0 {
            let token = "https://example.invalid/α?q=é&x=y";
            let both = format!("{s}{token}{s}");
            assert!(rendered(&both,|| Some(Ok(links(&both,&[token])))).is_ok());
        } else { assert!(rendered(&s,|| None).is_ok()); }
    }
}
#[test]
fn preserves_plaintext_markup_whitespace_and_literal_entities() {
    let s = "  **жирный** `код` <b>&amp;</b>\r\n\n[текст]('x')  ";
    assert_eq!(rendered(s,|| None).unwrap(), Value {
        id:"plain-id🧪".into(),
        html:"<div style=\"white-space: pre-wrap\">  **жирный** `код` &lt;b&gt;&amp;amp;&lt;/b&gt;\r\n\n[текст]('x')  </div>".into()
    });
}
#[test]
fn accepted_url_href_label_and_adjacent_boundaries() {
    let a = "http://example.invalid/测试?q=1&n=2";
    let b = "https://example.invalid/👩🏽‍🔬";
    let s = format!("{a}{b}");
    let t = rendered(&s,|| Some(Ok(links(&s,&[a,b])))).unwrap();
    let a = "http://example.invalid/测试?q=1&amp;n=2";
    assert_eq!(t.html,format!("<div style=\"white-space: pre-wrap\"><a href=\"{a}\">{a}</a><a href=\"{b}\">{b}</a></div>"));
    let u = format!("<{s}>");
    let x = rendered(&u,|| Some(Ok(links(&u,&["http://example.invalid/测试?q=1&n=2",b])))).unwrap();
    assert_eq!(x.html, t.html.replacen("><a ",">&lt;<a ",1).replacen("</a></div>","</a>&gt;</div>",1));
}
#[test]
fn rejected_scheme_absent_position_and_invalid_utf8_offset() {
    let s = "é ftp://example.invalid HTTPS://example.invalid http://example.invalid.";
    let output = rendered(s,|| {
        let p = s.find("http://").unwrap();
        let t = s.find("ftp://").unwrap();
        let u = s.find("HTTPS://").unwrap();
        Some(Ok(Node::Branch(vec![
            node(Some((1,3)),vec![]), node(None,vec![]),
            node(Some((t,t+"ftp://example.invalid".len())),vec![]),
            node(Some((u,u+"HTTPS://example.invalid".len())),vec![]),
            node(Some((p,s.len()-1)),vec![]),
        ])))
    }).unwrap();
    assert_eq!(output.html,"<div style=\"white-space: pre-wrap\">é ftp://example.invalid HTTPS://example.invalid <a href=\"http://example.invalid\">http://example.invalid</a>.</div>");
}
#[test]
fn unchanged_parser_error_and_no_url_shortcut() {
    let error = "synthetic parser error Ω".to_string();
    assert_eq!(rendered("ftp://",|| Some(Err(error.clone()))),Err(error));
    assert!(rendered("email@example.invalid www.example.invalid",|| None).is_ok());
}
#[test]
fn structural_append_calls_and_no_empty_slices() {
    let check = |s: &str, counts: (usize,usize,usize,usize)| {
        let (mut old,mut new) = (Trace::default(),Trace::default());
        stock::observe(s,&mut old); candidate::observe(s,&mut new);
        assert_eq!(old.text,new.text);
        assert_eq!((old.scalar,old.spans,new.scalar,new.spans),counts);
        let (mut old2,mut new2) = (Trace::default(),Trace::default());
        prior_product::observe(s,&mut old2); both::observe(s,&mut new2);
        assert_eq!((old2.text,old2.scalar,old2.spans),(old.text,old.scalar,old.spans));
        assert_eq!((new2.text,new2.scalar,new2.spans),(new.text,new.scalar,new.spans));
    };
    check("",(0,0,0,0));
    check("&<>\"",(0,4,0,4));
    let long = "x".repeat(131_072);
    check(&long,(131_072,0,0,1));
    let sparse = format!("{}&{}<{}","x".repeat(32768),"Ж".repeat(32768),"😀".repeat(32768));
    check(&sparse,(98_304,2,0,5));
    println!("R248_APPENDS 131072 1 98306 5");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stock", "prior", "dispatch", "rustc", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    stock, patch, prior, dispatch = (args.stock.read_bytes(), Path(__file__).with_name(
        "source.patch").read_bytes(), args.prior.read_bytes(), args.dispatch.read_bytes())
    for tag, buf in zip(("stock", "patch", "prior", "dispatch"), (stock, patch, prior, dispatch)):
        identity(tag, buf)
    check(b'if content.language == "text/plain" {\n            let root = plain::render(view, &content.source)?;'
          in dispatch, "exact content dispatch route")
    variants = compose(stock, patch, prior)
    rustc = args.rustc.resolve(strict=True)
    check(sha(rustc.read_bytes()) == RUSTC_SHA, "compiler digest")
    with tempfile.TemporaryDirectory(prefix="r248-", dir=args.work.resolve(strict=True)) as temp:
        root = Path(temp)
        env = {"PATH": "/usr/bin:/bin", "HOME": temp, "TMPDIR": temp, "LC_ALL": "C"}
        version = subprocess.check_output([rustc, "--version"], cwd=root, env=env,
                                          text=True, timeout=20).strip()
        check(version == RUSTC_VERSION, "compiler version")
        unit = root / "lift.rs"
        unit.write_text(constructs(stock) + "".join(lift(k, v) for k, v in variants.items()) + TESTS,
                        encoding="utf-8")
        results = {}
        for mode, flags in [("debug", []), ("optimized", ["-O"])]:
            exe = root / ("test-" + mode)
            subprocess.run([rustc, "--edition=2024", "--test", "-Dwarnings", *flags, unit, "-o", exe],
                           check=True, cwd=root, env=env, timeout=90)
            result = subprocess.run([exe, "--test-threads=1", "--nocapture"], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=90)
            check(result.returncode == 0, f"{mode}:\n{result.stdout}\n{result.stderr}")
            check("test result: ok. 8 passed; 0 failed;" in result.stdout, "test count")
            check("R248_APPENDS 131072 1 98306 5" in result.stdout, "append receipt")
            results[mode] = {"tests": 8, "generated_escape_and_render_four_arm_pairs": 4096,
                             "all_valid_unicode_scalars": 1112064,
                             "structural_unchanged_ascii_append_calls": [131072, 1],
                             "structural_sparse_mixed_append_calls": [98306, 5]}
    print(json.dumps({"status": "PASS", "rustc": version, "rustc_sha256": RUSTC_SHA,
                      "exact_composition_and_rollbacks_in_both_orders": True,
                      "real_recognition_and_ui_dependencies": False,
                      "results": results}, indent=2))


if __name__ == "__main__":
    main()
