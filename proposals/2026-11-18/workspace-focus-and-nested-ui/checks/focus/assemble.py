from pathlib import Path
import sys
s=Path(sys.argv[1]);v=(s/'crates/tabs/src/geometry.rs').read_text();sizes=(s/'crates/tabs/src/size.rs').read_text();f=Path(__file__).with_name('geometry.rs.in').read_text()
def sl(src,a,b):
 start=src.index(a);return src[start:src.index(b,start)]
rect=sl(v,'#[derive(Clone, Copy, Debug, PartialEq)]','/// Edge of a pane')
place=sl(v,'fn place(','impl TabLayout')
extents=sl(sizes,'pub(super) fn extents(','/// Gives the children' if '/// Gives the children' in sizes else '/// Gives children the lengths')
rects=sl(v,'    /// Every pane with its place in pixels','    /// Moves the divider')
c='if let Some((w,h))=area {let r=l.rects_spaced(w/scale,h/scale,1.); TabLayout::neighbor_in(&r,PaneId(1),edge)}else{l.neighbor(PaneId(1),edge)}' if 'fn neighbor_in(' in v else 'let _=(area,scale);l.neighbor(PaneId(1),edge)'
for a,b in [('RECT',rect),('PLACE',place),('EXTENTS',extents),('RECTS',rects),('CALL',c)]:f=f.replace('@'+a+'@',b)
Path(sys.argv[2]).write_text(f)
