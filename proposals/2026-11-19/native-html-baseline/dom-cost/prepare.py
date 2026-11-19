"""Extract the unchanged HTML5ever parse/normalization stage, ending before GPUI BlockNode conversion."""
import hashlib,shutil,sys
from pathlib import Path
root,out=map(Path,sys.argv[1:3]);asset=Path(__file__).resolve().parent
src=root/'vendor/gpui-base/src/text/format'
def check(p,expected):
    b=p.read_bytes()
    assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==expected,p
    return b.decode()
s=check(src/'html.rs','a4586b249303cc4eca901cdfb593bd43f5f41283')
mini=check(src/'html5minify/mod.rs','86fa5487380a1ebe808ba93d7117aa220b1eeda1')
main=(asset/'probe.rs').read_text()
start=s.index('    let opts = ParseOpts {',s.index('pub(crate) fn parse('))
end=s.index('        .map_err(',start)
parse=s[start:end].replace('    let dom = parse_document(', '    parse_document(')
cleanup=s[s.index('fn cleanup_html('):s.index('fn attr_value')]
# Same real parser and options; return its I/O result before UI-specific error mapping.
(out/'src').mkdir(parents=True,exist_ok=True)
(out/'src/html5minify.rs').write_text(mini)
(out/'src/main.rs').write_text(main.replace('/*INSERT_EXACT_STAGE*/',parse+'\n}\n'+cleanup.replace('super::html5minify::','html5minify::')))
for name in ['Cargo.toml','Cargo.lock']:shutil.copyfile(asset/name,out/name)
