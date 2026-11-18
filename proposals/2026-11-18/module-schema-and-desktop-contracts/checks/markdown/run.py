"""Reproduce with official markdown-rs 1.0.0 already built; no downloads, GUI, or clipboard."""
from pathlib import Path
import sys,subprocess,tempfile,hashlib
if len(sys.argv) not in (6,7): raise SystemExit("Usage: run.py BEFORE_MARKDOWN_RS AFTER_MARKDOWN_RS NODE_RS RANGE_HIGHLIGHT_RS MARKDOWN_RLIB [RUSTC]")
m01,m12,nodef,highf,lib=(Path(x).resolve() for x in sys.argv[1:6]); rust=sys.argv[6] if len(sys.argv)>6 else 'rustc'
def blob(p):
    d=p.read_bytes();return hashlib.sha1(b'blob '+str(len(d)).encode()+b'\0'+d).hexdigest()
assert blob(m01)=='ff38954bea1942bbc3a075b2fbbf19323acc4f4e'
assert blob(nodef)=='31cbc0a94aad24b3bf06805477dc5abd18cb71c7' and blob(highf)=='904bac25d90d8c4e35c6ed8cb546b51eac706371'
def fn(s,key):
    a=s.index(key);b=s.index('{',a);z=1
    for i in range(b+1,len(s)):
        z+=(s[i]=='{')-(s[i]=='}')
        if z==0:return s[a:i+1]
    assert False
template=Path(__file__).with_name('frame.rs.in').read_text()
for ver,src in [('before',m01),('after',m12)]:
    s=src.read_text(); node=nodef.read_text(); hl=highf.read_text()
    cx=s[s.index("Node::InlineCode(val) =>"):s.index('        Node::Link(val) =>',s.index("Node::InlineCode(val) =>"))]
    core='\n'.join(fn(s,'fn '+name+'(') for name in ['aligned_source_segments','source_char_offset','push_source_segment','code_source_segments'])
    if ver=='before':
        assert 'code_source_segments(source, &text, span, cx.offset, false)' in cx
        call='code_source_segments(source, &i.value, Some(Span { start: base+p.start.offset, end: base+p.end.offset }), base,false)'
    else:
        assert 'span\n                .zip(parse_cx.node_source(node))' in cx and 'inline_code_segments(raw, &text, span.start)' in cx
        core+='\n'+fn(s,'fn inline_code_segments(')
        call='inline_code_segments(&source[p.start.offset..p.end.offset], &i.value, base+p.start.offset)'
    code=template.replace('@@map@@',core).replace('@@call@@',call).replace('@@forward@@',fn(node,'fn source_range_for_segments(')).replace('@@inverse@@',fn(hl,'fn range_for_source(&self, source: &Range<usize>)'))
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp);(p/'gate.rs').write_text(code)
        subprocess.run([rust,'--edition=2024','-Awarnings',str(p/'gate.rs'),'-L',f'dependency={lib.parent}','--extern',f'markdown={lib}','-o',str(p/'gate')],check=True)
        subprocess.run([str(p/'gate'),ver],check=True)
