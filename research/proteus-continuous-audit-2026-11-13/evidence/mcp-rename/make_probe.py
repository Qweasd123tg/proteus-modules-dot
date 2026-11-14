from pathlib import Path
import argparse,hashlib,json
p=argparse.ArgumentParser();p.add_argument('--desktop',type=Path,default=Path('/workspace/scratch/3ba0fff8d310/desktop-behaviour'));p.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'));a=p.parse_args();r=Path(__file__).resolve().parent
hashes={}
for name in ['draft.rs','addons.rs','mcp.rs']:
 src=a.desktop/'src/settings'/name;data=src.read_bytes();(r/'probe/src/settings'/name).write_bytes(data);hashes[str(src.relative_to(a.desktop))]=hashlib.sha256(data).hexdigest()
(r/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
(r/'probe/Cargo.toml').write_text('''[package]\nname="mcp-rename-probe"\nversion="0.0.0"\nedition="2024"\n[workspace]\n[dependencies]\nproteus-contracts={path="'''+str(a.core.resolve()/'crates/proteus-contracts')+'''"}\nserde_json="1"\n''')
