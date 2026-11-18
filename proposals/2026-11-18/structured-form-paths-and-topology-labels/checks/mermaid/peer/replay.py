#!/usr/bin/env python3
"""Independently test two native Core formatters for ordinary quoted-node labels.
Usage: replay.py BEFORE AFTER EXPECTED_PATCH RUSTC; BEFORE contains helpers.rs and mermaid.rs.
Source-backed lexical/text oracle, not a full renderer. See NOTES.md.
"""
from pathlib import Path
import hashlib, itertools, os, re, subprocess, sys, tempfile
before,after,patch = map(Path,sys.argv[1:4])
rustc=sys.argv[4]
sha=hashlib.sha256(patch.read_bytes()).hexdigest()
assert sha=="6f3c5c6329d0d2b37155d340ec9bceec92b53be4cac9e064f763e773e2198c82"
old=(before/"mermaid.rs").read_text()
new=(after/"mermaid.rs").read_text()
def fn(s, key):
    i=s.index(key); j=s.index("\n}",i); return s[i:j+2]
old_helper=fn((before/"helpers.rs").read_text(),"fn mermaid_label(")
new_helper=fn(new,"fn quoted_node_label(")
method="pub fn render_topology_mermaid("
if method not in old: method="fn render_topology_mermaid("
old_render=fn(old,method)
new_render=fn(new,method)
assert new_render.count("quoted_node_label(")==5 and old_render.count("mermaid_label(")==6
assert new_render.replace("quoted_node_label(","mermaid_label(")==old_render
assert re.search(r'\{arrow\}\|\{\}\| \{to\}.*mermaid_label\(label\)',new_render)
base=['Research "Alpha"',r'C:\Notes',r'\\Studio\Notes', 'R&D', '#quot;', '#35;', '#38;', '#123;', '&quot;', '&amp;', 'Ångström', 'Фото', '🎵', 'style:C#', 'Status style:C#', 'Lifestyle: C#', 'classDef:Q#35;', 'lifestyle:R&D', 'style:α#', 'Music: Part II', 'classDefs - key:Photo#', 'plain', '"', chr(92), '#', '&']
# Nonempty labels only. No Markdown-string mode, markup, real records or external calls.
cases=list(dict.fromkeys(base+[" / ".join(g) for g in itertools.product(base,repeat=2)]+[a+b for a,b in itertools.product(base,repeat=2)]))
n_base=len(cases)
long_cases=[x+("::Палитра:Ångström:音色"*n)+y for n in [1,13,113,257] for x,y in [("studio::","::release"),("C:","::Research "+chr(34)+"Alpha"+chr(34)), ("A&B:","::v2"),("Research#:",":Folder"),("style:",":CLR#"),("classDef:","::C#"),("","::"+chr(92)+"notes"),("mood:","::R&D")]]
cases.extend(long_cases)
def inspect_graph_label(wire):
    # STR excludes double quote even after backslash. A node's opening and closing
    # quote must surround exactly one STR equal to its entire encoded payload.
    for prefix in ("style", "classDef"):
        wire=re.sub(prefix+r".*:\S*#.*;",lambda m:m[0][:-1],wire)
    if '"' in wire: return (False,None)
    # Mermaid 11.12.0 protects #word; before lexing, then turns protected spans
    # into named/numbered character references. Model the combined effect of
    # those two steps on the chosen labels without a Mermaid implementation. Interpret only inert ordinary
    # quote/ampersand/decimal character refs, once; this is NOT a renderer.
    def protect(m):
        n=m[1]
        return '&'+(('#'+n) if n.isdecimal() else n)+';'
    intermediate=re.sub(r'#([A-Za-z0-9_]+);',protect,wire)
    data=re.sub(r'&(quot|amp|#\d+);',lambda m: {'quot':'"', 'amp':'&'}.get(m[1]) if not m[1].startswith('#') else chr(int(m[1][1:])),intermediate)
    return (True,data)
with tempfile.TemporaryDirectory() as t:
    d=Path(t); p=d/'main.rs'
    p.write_text('use std::borrow::Cow; use std::io::BufRead;\n'+old_helper+'\n'+new_helper+'\n'+'''
fn main() {
    for label in std::io::stdin().lock().lines() {
        let label=label.unwrap();
        assert_eq!(matches!(quoted_node_label(&label), Cow::Borrowed(_)), !label.contains(['"', '#', '&']));
        println!("{}\\t{}", mermaid_label(&label), quoted_node_label(&label));
    }
}''')
    subprocess.run([rustc,'--edition=2024',str(p),'-o',str(d/'peer')],check=True)
    rows=subprocess.run([str(d/'peer')],input='\n'.join(cases)+'\n',capture_output=True,text=True,check=True).stdout.splitlines()
assert len(rows)==len(cases)
counts=[[0,0],[0,0]]
prev_good=retained=0
for ix, (label, row) in enumerate(zip(cases,rows)):
    old,new=row.split('\t')
    for stats,wire in zip(counts,[old,new]):
        lex,recovered=inspect_graph_label(wire)
        stats[0]+=int(not lex)
        stats[1]+=int(lex and recovered!=label)
    was_good=inspect_graph_label(old)==(True,label)
    prev_good+=int(was_good)
    retained+=int(was_good and inspect_graph_label(new)==(True,label))
    if ix+1==n_base:
        print("Original corpus:", n_base, "labels; before/after", counts)
    if label in base[:4]+["#quot;","#35;","style:C#","lifestyle:R&D","classDef:Q#35;"]:
        print(f"{label!r}: before={old!r}, after={new!r}")
assert sum(counts[0])>0 and counts[1]==[0,0]
print(f"patch={sha}; 5 quoted sites; edge and all other rendering statements unchanged.")
print(f"{len(cases)} distinct labels: not one quoted token {counts[0][0]} -> {counts[1][0]}; one token but wrong inert text {counts[0][1]} -> {counts[1][1]}.")
assert retained == prev_good
print(f"Original matching labels retained: {retained}/{prev_good}; {len(long_cases)} additional qualified names; max {max(map(len,long_cases))} code points. Native helper borrowed every input without quote/hash/ampersand.")
