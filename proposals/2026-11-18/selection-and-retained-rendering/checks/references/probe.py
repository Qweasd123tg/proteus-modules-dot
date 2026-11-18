"""Native markdown-rs 1.0.0, original Desktop partial-wrapper, no renderer or real clipboard."""
from pathlib import Path
import argparse, subprocess, tempfile
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('desktop',type=Path);p.add_argument('markdown_rlib',type=Path);p.add_argument('--rustc',default='rustc')
a=p.parse_args(); h=Path(__file__).resolve().parent; lib=a.markdown_rlib.resolve()
def show(name):
    return subprocess.check_output(['git','-C',a.desktop,'show','2307e9c67125bbe66f15ced51317a2dfcc437aa4:vendor/gpui-base/src/text/'+name],text=True)
src=show('node.rs')
start=src.index('pub(crate) fn wrap_with_mark');end=src.index('\n}\n',start)+2
md=show('format/markdown.rs');m=md[md.index('Node::LinkReference(link) =>'):];m=m[:m.index('text = merge_children_with_mark')]
for s in ('url: "".into()', 'title: link.label.clone().map(Into::into)', 'identifier: Some(link.identifier.clone().into())'): assert s in m
with tempfile.TemporaryDirectory() as tmp:
    t=Path(tmp);(t/'check.rs').write_text((h/'probe.rs.in').read_text().replace('/*WRAPPER*/',src[start:end]))
    subprocess.run([a.rustc,'--edition=2024',t/'check.rs','--extern',f'markdown={lib}','-L',f'dependency={lib.parent}','-o',t/'test'],check=True)
    subprocess.run([t/'test'],check=True)
