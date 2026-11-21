"""Extract the exact attachment and send/restore ownership boundary."""
import hashlib
from pathlib import Path
import shutil
import sys

source, arm, here = map(Path,sys.argv[1:])
s=source/"src"
d=arm/"src"
chat=s/"ui/chat"
d.mkdir(parents=True,exist_ok=True)
for name,to in {
    "harness.toml":"Cargo.toml","harness.lock":"Cargo.lock","probe.rs":"src/main.rs",
    "carrier.rs":"src/carrier.rs","cases.rs":"src/cases.rs",
}.items():
    shutil.copyfile(here/name,arm/to)
shutil.copyfile(chat/"attachment_io.rs",d/"attachment_io.rs")
shutil.copyfile(chat/"feedback/mod.rs",d/"feedback.rs")
# The exact native tests are retained in full tree; this gate is the non-test bin.
(d/"feedback").mkdir()
shutil.copyfile(chat/"feedback/tests.rs",d/"feedback/tests.rs")

def get(p): return p.read_text()
def put(p,s): p.write_text(s)
def cut(text,a,b):
    lo=text.index(a)
    return text[lo:text.index(b,lo+len(a))]
def func(text,a,indent=""):
    lo=text.index(a)
    return text[lo:text.index("\n"+indent+"}\n",lo)+3+len(indent)]
def digest(text):return hashlib.sha256(text.encode()).hexdigest()

gpui=get(source/"vendor/gpui-fast/src/platform.rs")
format=cut(gpui,"/// One of the editor's supported image formats", "/// An image, with a format and certain bytes")
image=cut(gpui,"/// An image, with a format and certain bytes", "pub(crate) fn decode_static_image(")
from_bytes=func(gpui,"    pub fn from_bytes(format: ImageFormat","    ")
hash_source=func(get(source/"vendor/gpui-fast/src/asset_cache.rs"),"pub fn hash<T: Hash>")
put(d/"image.rs",
    "use strum::EnumIter; use std::hash::{BuildHasher,Hash};\n"
    "mod collections { pub const FxBuildHasher: std::hash::BuildHasherDefault<std::hash::DefaultHasher> = std::hash::BuildHasherDefault::new(); }\n"
    +hash_source+format+image+"impl Image {\n"+from_bytes+"}\n"
)
attachments=get(chat/"attachments.rs")
types=cut(attachments,"/// One immutable raw image" if "impl Attachment {" in attachments else "/// An image of the draft", "\nimpl Chat {")
candidate="impl Attachment {" in attachments
owner = (
    "self.items.iter().map(|item|item.preview.bytes.len()).sum::<usize>(),"
    +("0" if candidate else "self.items.iter().map(|item|item.image.data.len()).sum::<usize>()")
)
put(d/"attachments.rs",
    "use std::sync::Arc; use proteus_contracts::domain::{ImageAttachment, MAX_IMAGE_BYTES, MAX_INPUT_IMAGES};\n"
    "use crate::{image::{Image,ImageFormat},attachment_io::{self,Budget,Prepared}};\n"
    +types+
    "\nimpl Attachments { pub fn mount(&mut self, p: Prepared) -> Result<(),String> {self.add_prepared(p)} pub fn detach(&mut self,i:usize){self.remove(i);} "
    "pub fn backing(&self)->(usize,usize){("+owner+")} "
    "pub fn raw_pointers(&self)->Vec<usize>{self.items.iter().map(|item|item.preview.bytes.as_ptr() as usize).collect()} "
    "pub fn remaining(&self)->Budget {self.budget()} }\n"
)
actions=get(chat/"actions.rs")
send=cut(actions,"    pub(super) fn send(", "    pub(super) fn stop(")
# Same initial send guards and all receipt-request construction before native composer/UI work.
begin=cut(send,"        if self.readonly.is_some()","        self.clear_notice")
begin=begin.replace('            return;','            return None;')
assert begin.count('uuid::Uuid::new_v4().simple()')==1
begin=begin.replace('uuid::Uuid::new_v4().simple()','uuid::Uuid::from_u128(self.next_request).simple()')
prepared="        let images = draft.images();\n" if candidate else ""
body=send[send.index(".spawn(async move { api.send" if not candidate else ".spawn(async move {\n                    let mut request"):].split(".await;",1)[0].strip()
assert body.startswith(".spawn(async move {") and body.endswith(")")
# Keep the exact existing worker body, making its already-async seam explicit in the probe.
worker=body.removeprefix(".spawn(")[:-1]
after=cut(send,"                        let message_id = result", "                    })\n                })")
after=after.replace("                        let Err(error) = result else {","                        let Err(error) = result else {",1)
draft=get(chat/"draft.rs")
draft=draft[draft.index("/// A complete unsent message"):]
put(d/"send.inc.rs",
    draft.replace("Context<Self>","Context")+"\nimpl Chat {\n"
    "fn stage(&mut self,window:&mut Window,cx:&mut Context)->Option<Pending> { self.next_request+=1;\n"+begin+
    "        let Some(api)=self.api.clone() else {return None;};\n"+prepared+
    "        let execute = "+worker+";\n"
    "        Some(Pending { id: request_id, draft_text, draft, execute:Some(Box::new(move || run_background(execute))) })\n"
    "}\n"
    "fn finished(&mut self,pending: Pending,result:anyhow::Result<serde_json::Value>,window:&mut Window,cx:&mut Context) {\n"
    "        let Pending {id:request_id,draft_text,draft,..}=pending; let this=self;\n"+after+"\n}\n"
    "}\n"
)
for label,value in (
    ("source-capped-read",get(chat/"attachment_io.rs").split("pub(super) fn read_batch",1)[1]),
    ("receipt-and-echo-lifecycle",get(chat/"feedback/mod.rs").split("    pub fn visible_sends",1)[1]),
    ("draft-restore",draft),("actual-send-completion",after),
    ("send-guards",begin.split("        let draft =",1)[0]),
    ("image-mime",format),("image-source-constructor",from_bytes),
):
    print(digest(value)+"  "+label)
