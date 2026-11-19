#!/usr/bin/env python3
"""Compile standalone R8 tests against trees supplied to --src; not a full product or checkout test.
The compiler consumes already built Proteus-core Cargo dependency artifacts; no network or cargo fetch."""
import argparse, json, os, shutil, subprocess
from pathlib import Path
h=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument("--src",required=True,type=Path);p.add_argument("--deps",required=True,type=Path);p.add_argument("--rustc",required=True);p.add_argument("--out",required=True,type=Path);a=p.parse_args()
src=a.src.resolve()/"crates/proteus-core/src"; d=a.out.resolve();d.mkdir(parents=True,exist_ok=True);base=a.deps.resolve()
for rel in ('app_server/transcript.rs','app_server/transcript','core/session_store/remote','core/session_store/context_summary.rs','core/session_store/path_identity.rs','process_adapters/invocation_error.rs'):
 dest=d/rel;dest.parent.mkdir(parents=True,exist_ok=True)
 if (src/rel).is_dir():shutil.copytree(src/rel,dest,dirs_exist_ok=True)
 else:shutil.copyfile(src/rel,dest)
dest=d/'core/session_store/path_identity.rs';dest.write_text(dest.read_text().split('#[cfg(test)]')[0])
dest=d/'core/session_store/remote/view/tests.rs';dest.write_text(dest.read_text()+'\n'+(h/'core_controls.rs').read_text())
dest=d/'core/session_store/remote/view/tests/support.rs';s=dest.read_text()
def edit(old,new):
 global s
 assert s.count(old)==1,old
 s=s.replace(old,new)
edit('    handles: u64,','    pub(super) r8_page_cap: u32,\n    pub(super) r8_wrong_snapshot_at: Option<u64>,\n    pub(super) r8_advance_at_publish: bool,\n    handles: u64,')
edit('            handles: 0,','            r8_page_cap: 64, r8_wrong_snapshot_at: None, r8_advance_at_publish: false, handles: 0,')
edit('.take(limit as usize)','.take(limit.min(state.r8_page_cap) as usize)')
edit('                Ok(Response::Records {','                let mut snapshot=snapshot; if state.r8_wrong_snapshot_at==Some(after_seq) { snapshot.snapshot_id="other".into(); }\n                Ok(Response::Records {')
edit('                if !current(&state, &source) || (state.fail_head','                if state.r8_advance_at_publish && key=="display-view-v1-head" {state.r8_advance_at_publish=false;drop(state);self.append(1);return Ok(Response::CacheWritten {etag: None});}\n                if !current(&state, &source) || (state.fail_head')
dest.write_text(s)
(d/'test.rs').write_text((h/'test_root.rs').read_text())
fp=base/'.fingerprint';ref=json.loads(next(fp.glob('proteus-core-*/test-lib-proteus_core.json')).read_text());flags=[]
for _,name,_,key in ref['deps']:
 if name=='build_script_build':continue
 paths=list((base/'deps').glob(f'lib{name}-*.rlib')) or list((base/'deps').glob(f'lib{name}-*.so'))
 if len(paths)>1:
  paths=[path for path in paths if any(x.read_text()==key.to_bytes(8,'little').hex() for x in fp.glob(f'*-{path.stem.split("-")[-1]}/lib-{name}'))]
 assert len(paths)==1,name
 flags+=['--extern',f'{name}={paths[0]}']
cmd=[a.rustc,'--edition=2024','--test',str(d/'test.rs'),'-C','opt-level=0','-C','codegen-units=4','-C','debuginfo=0','-A','warnings','-L',f'dependency={base}/deps','-L',f'native={next((base/"build").glob("ring-*/out/libring_core*.a")).parent}',*flags,'-o',str(d/'check')]
subprocess.run(cmd,check=True)
subprocess.run([str(d/'check'),'r8_','--test-threads=1'],check=True)
