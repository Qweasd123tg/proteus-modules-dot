"""Independent offline label-state + grammar contract, NOT the complete Mermaid library.
Usage: python3 replay.py BEFORE/mermaid.rs AFTER/mermaid.rs BEFORE/helpers.rs [rustc]"""
from itertools import product
from pathlib import Path
import hashlib, re, subprocess, sys, tempfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
base,target,helpers=map(Path,sys.argv[1:4]);rust=sys.argv[4] if len(sys.argv)>4 else 'rustc'
def blob(p):
    b=p.read_bytes();return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
assert blob(base)=='35f38a61c0401699f2509765f8019d764e82fe98' and blob(target)=='ba8e84d1eead90f70a92db7454ac8744e6c35398'
assert blob(helpers)=='f7fa50d31165177c9e96a454000090a5aff4ff1e'
def fn(s,q):
    i=s.index(q);n=s.index('{',i);j=s.index('\n}',n)+2
    return s[i:j]
# Test-only equivalent of official Mermaid 11.12.0 utils.ts:906-918; fixture text is ordinary node labels, never class/style statements.
def protect(m):
    w=m[0][1:-1];return ('ﬂ°°' if w.isascii() and w.isdigit() else 'ﬂ°')+w+'¶ß'
def lexer(q):
    # flow.jison:82-87,272-282. Input is only the *already delimited* contents
    # between the two node shape boundaries. This test is NOT a Mermaid parser.
    # Fixtures do not use backtick-style Markdown labels or unquoted nested shapes.
    # The official style/classDef substitutions are not anchored to directives;
    # run both even on ordinary labels. They remove the matched final semicolon.
    for word in ('style','classDef'):
        q=re.sub(word+r'.*:\S*#.*;',lambda m:m[0][:-1],q)
    q=re.sub(r'#\w+;',protect,q,flags=re.ASCII);t=[];state='text';i=0
    while i<len(q):
        if q[i]=='"':
            if state=='text' and q[i:i+2]=='"`':raise ValueError('unsupported Markdown-string fixture')
            state='string' if state=='text' else 'text';i+=1;continue
        if state=='text':m=re.match(r'[^\[\](){}|"]+',q[i:])
        else:m=re.match(r'[^"]+',q[i:])
        if not m:raise ValueError('outside this fixture grammar')
        t.append(('STR' if state=='string' else 'TEXT',m[0]));i+=len(m[0])
    if state!='text' or not t:raise ValueError('unbalanced or empty selection')
    # flow.jison 'text : textToken | text textToken | STR | MD_STR'; where
    # textToken may include TEXT but never STR. The fixture uses no other tokens.
    if any(tag=='STR' for tag,v in t[1:]):raise ValueError('STR cannot follow another text token')
    payload=''.join(v for _,v in t)
    # Model the documented Mermaid entity round-trip for a plain-text label:
    # XML-escape literal text and restore protected entities just once. This
    # checks semantic text, NOT browser htmlLabels layout/sanitization.
    encoded=escape(payload).replace('ﬂ°°','&#').replace('ﬂ°','&').replace('¶ß',';')
    return ET.fromstring('<t>'+encoded+'</t>').text or ''
def expected(x):return [('config<br/>'+ (x if x.strip() else 'default')),('draft<br/>'+x),x,x+' note','display<br/>'+x]
def slice_nodes(graph):
    rows=[];structure=[]
    for line in graph.splitlines():
        line=line.strip()
        m=re.fullmatch(r'(n\d+)\(\[(.*)\]\)',line) or re.fullmatch(r'(n\d+)\[(.*)\]',line)
        if m:rows.append(m[2]);structure.append(m[1]+' NODE')
        else:structure.append(line)
    assert len(rows)==5
    return rows,structure
# Five real output locations, including ordinary path, quotes, entity-looking filenames and neutral Unicode.
plain=['Notes','Résumé Ω','猫 📘','STYLE: ordinary','classDefinition: text','v2:notes','  padded  ']
punct=['"Alpha"','Site "Alpha" notes',r'C:\Notes',r'work\chapter\draft.md','style:C#','lifestyle:R&D','lifestyle:Q#35;','CLASSDEF:Q#35;','ClassDef:C#','classDef:Q#35;','#quot;','#35;','#9829;','&amp;','&quot;','&#35;','R&D','issue #42','A "Б" · C:\\Notes','']
cases=list(dict.fromkeys(plain+punct+['room '+a+' '+b+' note' for a,b in product(punct[:-1],repeat=2)]))
with tempfile.TemporaryDirectory() as td:
    tmp=Path(td);frame=Path(__file__).with_name('frame.rs.in').read_text()
    h=helpers.read_text();h='\n'.join(fn(h,'pub(super) fn '+n+'(') for n in ['mermaid_label','ordered_slots'])
    allgraphs={}
    for stage,p in [('before',base),('after',target)]:
        renderer=p.read_text();src=frame.replace('@@helpers@@',h).replace('@@renderer@@',renderer);f=tmp/'gate.rs';f.write_text(src)
        exe=tmp/'probe'
        subprocess.run([rust,'--edition=2024','-Awarnings',str(f),'-o',str(exe)],check=True)
        if stage=='before':
            # Give the baseline the identical in-patch native test. It must fail at the graph.contains assertion.
            nt=target.read_text().split('#[cfg(test)]')[1];f.write_text(src.replace(renderer,renderer+'\n#[cfg(test)]'+nt))
        subprocess.run([rust,'--edition=2024','--test','-Awarnings',str(f),'-o',str(tmp/'native')],check=True)
        result=subprocess.run([str(tmp/'native')],capture_output=True,text=True)
        assert (result.returncode==0)==(stage=='after'),result.stdout
        if stage=='before':assert 'assertion failed: graph.contains(' in result.stdout
        total=same=invalid=0
        for x in cases:
            rows,structure=slice_nodes(subprocess.check_output([str(exe),x],text=True))
            if stage=='before':allgraphs[x]=structure
            else:assert allgraphs[x]==structure
            for i,(q,want) in enumerate(zip(rows,expected(x))):
                if want=='':continue # empty tool names are outside the ordinary label contract
                try: got=lexer(q)
                except (ValueError,ET.ParseError):got=None;invalid+=1
                total+=1;same+=got==want
                if stage=='after':assert got==want,(q,want,got)
                if i==0 and x in ['Site "Alpha" notes',r'C:\Notes','#quot;','&amp;','Résumé Ω']:
                    print(f'{stage}: {x} | emitted: {q} | recovered: {got if got is not None else "[invalid token sequence]"}')
        print(f'{stage}: {same}/{total} ordinary node texts recovered, {invalid} outside the accepted node-text grammar or undecodable. Identically applied in-tree Rust test: '+('PASS' if result.returncode==0 else 'RED (assertion)'))
        if stage=='before':assert same<total
    print(f'Unchanged non-caption graph structure on all {len(cases)} fixture graphs; edges/classes and IDs matched.')
