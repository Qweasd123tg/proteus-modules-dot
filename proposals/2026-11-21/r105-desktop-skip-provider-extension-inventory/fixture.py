"""Create a ready-like provider fixture with inert files that are never executed."""
import hashlib
import json
from pathlib import Path
import sys

root=Path(sys.argv[1])
ready=root/"ready"
receipt=root/"receipt"
for d in (ready,receipt):
    (d/"bin").mkdir(parents=True)
(root/"home").mkdir()
(root/"path").mkdir()
(ready/"bin"/"proteus").write_bytes(b"inert backend marker")
for d,n,b in [(ready,"shared",b"inert shared provider"),(ready,"fixed",b"inert fixed provider"),
              (ready,"tampered",b"changed inert provider"),(receipt,"provider",b"inert receipt provider")]:
    (d/"bin"/n).write_bytes(b)

def mod(d,id,cmd,title=None,*,name=None,version="1",auth=False,named=True,sha=None,icon=None):
    dest=d/"share/modules"/id
    dest.mkdir(parents=True)
    selected=d/cmd
    template={
       "id":"fixture", "title":title, "description":"synthetic metadata only",
       "module_id":"fixture-model", "module_config":{"kind":"synthetic","enabled":True},
       "env_allowlist":["PATH","INERT_PROVIDER_VARIABLE"],
    }
    if auth:
        template["auth"]={"command":["metadata-only","status"],"credential_file_key":"inert_locator"}
    m={
      "id":name or id,"version":version,"command":[cmd,"--inert"],
      "exports":{"model":["*" if named else "fixture-model"]},
      "sha256":sha if sha is not None else hashlib.sha256(selected.read_bytes()).hexdigest(),
      "model_connections":[template] if title is not None else [],
    }
    if icon:
        m["icon"]=icon
    (dest/"module.json").write_text(json.dumps(m),encoding="utf-8")

mod(ready,"alpha-first","bin/shared","A shared",auth=True,icon="./logo.svg")
mod(ready,"zulu-duplicate","bin/shared","Z duplicate")
mod(ready,"mismatched","bin/fixed","B fixed",version="",name="manifest-id",named=False)
mod(ready,"tampered","bin/tampered","bad program digest",sha="0"*64)
mod(ready,"missing-program","bin/missing","missing executable",sha="1"*64)
mod(ready,"nonprovider","bin/not-present",sha="unread")
mod(ready,"outside-relative","../not-present","bad scope",sha="2"*64)
mod(receipt,"explicit","bin/provider","C receipted",
    sha=hashlib.sha256((receipt/"bin/provider").read_bytes()).hexdigest().upper(),icon="lucide:plug")
mdir=ready/"share/modules"
(mdir/"sdk-dir").mkdir()
(mdir/"not-directory").write_bytes(b"inert")
(mdir/"malformed").mkdir()
(mdir/"malformed/module.json").write_text("{bad",encoding="utf-8")
(mdir/"oversize").mkdir()
(mdir/"oversize/module.json").write_bytes(b" "*(128*1024+1))
