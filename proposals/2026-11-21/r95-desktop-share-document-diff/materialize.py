"""Typed production declaration and exact DiffView handoff over a native-effect carrier."""
import hashlib
import shutil
import sys
from pathlib import Path

source,out,packet=map(Path,sys.argv[1:])
dst=out/"src"
schemas=dst/"declarative"
schemas.mkdir(parents=True)
d,u=source/"src/declarative",source/"src/ui/extensions/declarative"
for name in "widget control graph tree list lanes protocol session presentation icons".split():
    shutil.copyfile(d/(name+".rs"),schemas/(name+".rs"))
shutil.copytree(source/"crates/diff",out/"crates/diff",symlinks=True)
shutil.copyfile(source/"LICENSE-GPL",out/"LICENSE-GPL")
for a,b in (("harness.toml","Cargo.toml"),("harness.lock","Cargo.lock"),("carrier.rs","src/carrier.rs"),
            ("probe.rs","src/main.rs"),("cases.rs","src/cases.rs")):
    shutil.copyfile(packet/a,out/b)

def between(text,a,b):
    i=text.index(a)
    return text[i:text.index(b,i+len(a))]
view=(source/"src/ui/diff/mod.rs").read_text()
file=(source/"src/ui/diff/file.rs").read_text()
fields=(u/"fields.rs").read_text()
widget=(d/"widget.rs").read_text()
protocol=(d/"protocol.rs").read_text()
shared="enum PatchSource" in view
decl=between(view,"/// The complete original input" if shared else "pub(in crate::ui) struct DiffView {","    fn split(&self)")
(dst/"diff.inc.rs").write_text(decl.replace("pub(in crate::ui)","pub(crate)")+"}\n")
arm=between(fields,"            Node::Diff {\n                id, patch","            Node::Graph {")
(dst/"fields.inc.rs").write_text("""
impl DeclarativeView {
    fn sync_document(&mut self, node: &Node, cx: &mut Context<Self>) {
        match node {
"""+arm+"""
            _ => panic!("document diff seam only"),
        }
    }
}
""")
all_b=between(view,"                kit::button(\"copy-diffs\")","            )\n    }")
i=all_b.index("                    .disabled(")
all_chain=all_b[i:].rstrip().removesuffix(",")
(dst/"copy-all.inc.rs").write_text("impl DiffView {\nfn copy_all(&self, cx:&mut Context<Self>)->CopyAll {\nCopyAll::default()\n"+
    all_chain+"\n}\n}\n")
per_b=between(file,"                            .disabled(file.patch.is_empty())","                    ),\n")
(dst/"copy-file.inc.rs").write_text("fn copy_file(file:Rc<File>,cx:&mut Context<DiffView>)->CopyFile {\nCopyFile::default()\n"+
    per_b.rstrip().removesuffix(",")+"\n}\n")
(dst/"owner.inc.rs").write_text("""
const SHARED:bool=true;
fn weak(v:&DiffView)->Option<std::sync::Weak<String>> {
    match &v.patch { PatchSource::Document(p)=>Some(Arc::downgrade(p)), _=>None }
}
fn is_owned(v:&DiffView)->bool{ matches!(v.patch, PatchSource::Embedded(_)) }
""" if shared else """const SHARED:bool=false;
fn weak(_: &DiffView)->Option<std::sync::Weak<String>>{None}
fn is_owned(_: &DiffView)->bool{true}
""")
scopes={
    "diff-wire-guard": between(widget,"            Node::Code {\n                height: Some(height)","            Node::Graph {"),
    "protocol-parser": between(protocol,"pub fn parse(","/// View id of a surface"),
    "untouched-reconciliation": between(view,"        self.info = info.to_vec();","    fn split(&self)"),
    "unchanged-view-rest": view[view.index("    fn split(&self)"):].replace(all_b,""),
    "render-setup": between(view,"        let list = scrollable.then","    pub fn set_patch("),
    "other-fields": fields.replace(arm,""),
    "per-file-render":file,
    "diff-parser":(source/"crates/diff/src/parse.rs").read_text(),
    "embedded-chat-caller":between((source/"src/ui/chat/thread.rs").read_text(),"    pub(super) fn prepare_tool_diffs(","\n}\n"),
}
for label,text in scopes.items(): print(hashlib.sha256(text.encode()).hexdigest(),label)
