#!/usr/bin/env python3
"""Usage: python verify.py ORIGINAL_DESKTOP PATCHED_DESKTOP [--rustc rustc] [--pandoc pandoc].
No network, Git commands, project builds, GUI, or clipboard. Only the selected cell serializer
is compiled, with selected-source strings in place of UI selection state. Requires Rust and
Pandoc with the GFM reader. All build outputs are created in a private temporary directory."""
import argparse
import subprocess
import tempfile
from pathlib import Path
from xml.etree.ElementTree import fromstring, ParseError

P = argparse.ArgumentParser(description=__doc__)
P.add_argument('original', type=Path); P.add_argument('patched', type=Path)
P.add_argument('--rustc', default='rustc'); P.add_argument('--pandoc', default='pandoc')
args = P.parse_args()
relative = Path('vendor/gpui-base/src/text/node.rs')
def rust_fn(src, name):
    i = src.index('fn ' + name + '(')
    return src[i:src.index('\n}\n', i)+2] + '\n'
def out(cmd, **kw):
    return subprocess.check_output(cmd, text=True, **kw)
prefix=r'''
#![allow(dead_code)]
#[derive(Clone,Copy)] enum ColumnumnAlign {None, Left, Center, Right}
struct Paragraph(String);
impl Paragraph {fn selected_source(&self)->String{self.0.clone()}}
struct TableCell {children:Paragraph}
struct TableRow {children:Vec<TableCell>}
struct Table {children:Vec<TableRow>}
impl Table {fn column_align(&self,i:usize)->ColumnumnAlign{if i==0{ColumnumnAlign::Left}else{ColumnumnAlign::Right}}}
'''
driver=r'''
fn main() {
    let args:Vec<_>=std::env::args().skip(1).collect();
    let position:usize=args[0].parse().unwrap();
    let mut cells=if args[2]=="single"{["","","",""]}else{["Key","Count","Alice","17"]};
    cells[position]=args[1].as_str();
    let table=Table{children:cells.chunks(2).map(|row|TableRow{children:row.iter().map(|s|
        TableCell{children:Paragraph((*s).to_owned())}).collect()}).collect()};
    print!("{}",table_selected_source(&table));
}
'''
def build(root, work, name):
    source=(root/relative).read_text()
    helper=rust_fn(source,'protect_table_pipes') if 'fn protect_table_pipes(' in source else ''
    f=work/(name+'.rs'); f.write_text(prefix+helper+rust_fn(source,'table_selected_source')+driver)
    binary=work/name
    subprocess.run([args.rustc,'--edition=2024',str(f),'-o',str(binary)],check=True)
    return binary
def boundaries(row):
    # Independent narrow model of markdown-rs 1.0.0 head/body row data and
    # escape states. Once inside a cell, a backslash consumes a following
    # backslash or pipe; unconsumed pipes delimit columns. This is not an
    # inline parser. Original upstream sources and tests:
    # https://github.com/wooorm/markdown-rs/blob/1.0.0/src/construct/gfm_table.rs#L734-L766
    # https://github.com/wooorm/markdown-rs/blob/1.0.0/tests/gfm_table.rs#L1792-L1837
    i=0; marks=[]
    while i<len(row):
        if row[i]=='\\' and row[i+1:i+2] in ('\\','|'): i+=2;continue
        if row[i]=='|': marks.append(i)
        i+=1
    return marks
for n in range(7):
    assert len(boundaries('a'+'\\'*n+'|b'))==(n%2==0)
def html(source):
    data=out([args.pandoc,'-f','gfm','-t','html5'],input=source)
    try: root=fromstring(data)
    except ParseError: return []
    if root.tag!='table':return []
    return [(''.join(el.itertext()),tuple(n.tag for n in el.iter() if n is not el))
            for el in root.iter() if el.tag in ('th','td')]
def observe(binary,position,payload,expected,mark):
    result=out([str(binary),str(position),payload,'multi'])
    assert out([str(binary),str(position),payload,'single'])==payload
    rows=result.splitlines()
    structure=len(rows)==3 and all(len(boundaries(r))==3 for r in rows)
    parsed=html(result); cells=[('Key',()),('Count',()),('Alice',()),('17',())]
    same_neighbors=len(parsed)==4 and all(parsed[i]==cells[i] for i in range(4) if i!=position)
    exact=same_neighbors and parsed[position]==(expected,mark)
    return structure,same_neighbors,exact
print(out([args.rustc,'--version']).strip(),out([args.pandoc,'--version']).splitlines()[0])
with tempfile.TemporaryDirectory() as tmp:
    work=Path(tmp)
    binaries=[build(args.original,work,'before'),build(args.patched,work,'after')]
    totals=[[0,0,0],[0,0,0]]; reg=[0,0,0]
    samples=0
    for n in range(7):
        for fence,mark in [('',()),('`',('code',)),('**',('strong',))]:
            value='x'+'\\'*n+'|y'
            for position in range(4):
                case=[observe(b,position,fence+value+fence,value,mark) for b in binaries]
                for s in (0,1):
                    for j in range(3):totals[s][j]+=int(case[s][j])
                for j in range(3):reg[j]+=int(case[0][j] and not case[1][j])
                samples+=1
    print('Cases:',samples,'(four header/body positions, plain/code/bold, 0–6 preceding backslashes).')
    print('Pass counts [native-rule boundaries, Pandoc unchanged neighbors, Pandoc exact visible selected content and marks]')
    print('before',totals[0],'after',totals[1],'pass→fail',reg)
    print('One selected cell returned the original unwrapped cell string in every comparison.')
    assert totals[0][0]<samples and totals[1][0]==samples and totals[1][1]==samples and reg==[0,0,0]
