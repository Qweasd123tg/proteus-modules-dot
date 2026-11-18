"""Capture actual renderer marker/checkbox construction without GPUI painting."""
import argparse,pathlib,subprocess,tempfile
p=argparse.ArgumentParser()
p.add_argument('source',type=pathlib.Path,help='Desktop source root')
p.add_argument('markdown_rlib',type=pathlib.Path,help='official markdown-rs 1.0.0 rlib')
p.add_argument('--rustc',default='rustc')
p.add_argument('--dependency',action='append',default=[],help='directories with transitive rlibs')
args=p.parse_args()
d=args.source/'vendor/gpui-base/src/text'
node=(d/'node.rs').read_text()
doc=(d/'document.rs').read_text()
utils=(d/'utils.rs').read_text()
frame=pathlib.Path(__file__).with_name('frame.rs.in').read_text()
def within(s,a,b):return s[s.index(a):s.index(b,s.index(a))]
opts=within(doc,'#[derive(Default, Clone, Copy)]\npub(crate) struct NodeRenderOptions','/// The kind of block')
prefix=within(utils,'const NUMBERED_PREFIXES_1','/// Decodes a')
row=within(node,'    fn render_list_item_row(','    fn render_list_item(')
item=within(node,'    fn render_list_item(','    /// Render a Markdown table.')
list_arm=within(node,'            BlockNode::List {\n                children,\n                ordered,\n                start,\n                ..\n            } => div()', '            BlockNode::CodeBlock(code_block) => code_block.render')
for key,data in [('OPTIONS',opts),('PREFIX',prefix),('ROW',row),('ITEM',item),('LISTARM',list_arm)]:
 assert frame.count('@'+key+'@')==1
 frame=frame.replace('@'+key+'@',data)
with tempfile.TemporaryDirectory() as t:
 src=pathlib.Path(t)/'capture.rs'; out=pathlib.Path(t)/'capture'
 src.write_text(frame)
 cmd=[args.rustc,'--edition','2024',str(src),'--extern',f'markdown={args.markdown_rlib.resolve()}']
 for lib in [args.markdown_rlib.parent]+[pathlib.Path(d) for d in args.dependency]:
  cmd.extend(['-L',f'dependency={lib.resolve()}'])
 subprocess.run(cmd+['-o',str(out)],check=True)
 raise SystemExit(subprocess.run([str(out)]).returncode)
