"""python3 run.py MARKDOWN_RS NODE_RS RANGE_HIGHLIGHT_RS LIBMARKDOWN_RLIB [RUSTC]"""
import pathlib,subprocess,tempfile,sys
from pathlib import Path
m,n,h,lib=map(Path,sys.argv[1:5]);m=m.read_text();n=n.read_text();h=h.read_text();base=Path(__file__).resolve().parent
def fn(text,head,lead):
    a=text.index(head);b=text.index('\n'+lead+'}',a)+2+len(lead);return text[a:b]
a=m[m.index('fn aligned_source_segments('):m.index('fn decoded_entity(')]
cs=fn(m,'fn code_source_segments(',''); cond='fn inline_code_segments(' in m
if cond:cs+='\n'+fn(m,'fn inline_code_segments(','')
arm=m[m.index('        Node::InlineCode(val) => {'):m.index('        Node::Link(val) =>',m.index('        Node::InlineCode(val) => {'))]
if cond:assert 'inline_code_segments(raw, &text, span.start)' in arm and '.zip(parse_cx.node_source(node))' in arm
else:assert 'code_source_segments(source, &text, span, cx.offset, false)' in arm
src=(base/'oracle.rs.in').read_text().replace('@MAPPERS@',a+cs+'\n'+fn(n,'fn source_range_for_segments(','' )).replace('@INVERSE@',fn(h,'fn range_for_source(&self, source: &Range','    ')+'\n'+fn(h,'fn push_source_segments(', '    ')).replace('@PARSECX@',(base/'parse-context.rs.in').read_text()).replace('@SOURCE@','inline_code_segments(cx.node_source(node).unwrap(),&v.value,absolute.start)' if cond else 'code_source_segments(&source,&v.value,Some(absolute),offset,false)')
with tempfile.TemporaryDirectory() as td:
 p=Path(td);f=p/'gate.rs';f.write_text(src);subprocess.run([sys.argv[5] if len(sys.argv)>5 else 'rustc','--edition=2024','-Awarnings',str(f),'-O','-L',f'dependency={lib.parent}','--extern',f'markdown={lib}','-o',str(p/'test')],check=True);sys.exit(subprocess.run([str(p/'test')]).returncode)
