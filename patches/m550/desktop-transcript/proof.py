"""Reproduce scoped native differential checks from the sealed source inputs. Python3.10+."""
import argparse,base64,gzip,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
pkg=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--vendor',type=Path,help='optional offline Cargo vendor directory');args=ap.parse_args()
receipt=json.loads((pkg/'receipt.json').read_bytes())
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def sl(s,a,b):
 assert s.count(a)==1,a
 return s[s.index(a):s.index(b,s.index(a))]
def typ(s,a):
 i=s.index(a);return s[s.rindex('#[derive(',0,i):s.index('\n}',i)+2]
def apply(base,patch,root):
 f=root/'src/transcript/mod.rs';f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(base)
 for flag in (['--check'],[]):subprocess.run(['git','apply',*flag,'-'],cwd=root,input=patch,check=True)
 out=f.read_bytes();subprocess.run(['git','apply','-R','-'],cwd=root,input=patch,check=True);assert f.read_bytes()==base
 return out
inputs=json.loads(gzip.decompress(base64.b64decode((pkg/'sources.json.gz.b64').read_bytes())))
assert set(inputs)==set(receipt['input_blobs'])
assert all(blob(s.encode())==receipt['input_blobs'][n] for n,s in inputs.items())
B='crates/proteus-contracts/src/'
def get(n):return inputs[B+n]
with tempfile.TemporaryDirectory() as td:
 root=Path(td);common=root/'common';common.mkdir()
 m=apply(inputs['desktop-current'].encode(),inputs['composition-522'].encode(),root/'compose')
 assert blob(m)==receipt['m350_target_git_blob']
 patches={n:(pkg/f'{n}.patch').read_bytes() for n in ('borrowed','local')}
 assert all(sha(b)==receipt['patch_sha256'][n] for n,b in patches.items())
 arms={'stock':m}
 for side,patch in patches.items():arms[side]=apply(m,patch,root/'compose')
 arms['combined']=apply(arms['borrowed'],patches['local'],root/'compose')
 assert arms['combined']==apply(arms['local'],patches['borrowed'],root/'compose')
 for n in ['exercise','meter']:shutil.copyfile(pkg/f'{n}.rs',common/f'{n}.rs')
 (common/'app_protocol.rs').write_text(get('app_protocol/transcript.rs'))
 (common/'contracts.rs').write_text('use serde::{Deserialize,Serialize};use uuid::Uuid;\n'+typ(get('contracts/tool_terminal.rs'),'pub struct ToolTerminalRef'))
 (common/'domain.rs').write_text('use std::path::PathBuf;use serde::{Deserialize,Serialize};use uuid::Uuid;\n'+''.join(sl(get('domain/ids.rs'),f'pub type {n} = ','\n')+'\n' for n in ('MessageId','ThreadId','SessionId'))+typ(get('domain/image.rs'),'pub struct ImageRef'))
 (common/'model_standard.rs').write_text('use serde::{Deserialize,Serialize};\n'+typ(get('model_standard/content_part.rs'),'pub enum MessagePhase'))
 for side,bb in arms.items():
  assert blob(bb)==receipt['scoped_target_blobs'][side]
  s=bb.decode();t=(s[s.index('use std::'):s.index('use proteus_contracts')]+'use crate::app_protocol::{AppTranscriptMessage,AppTranscriptTool,AppTranscriptSubagent};\nuse crate::domain::{ImageRef,ThreadId,MessageId};\n'+sl(s,'#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]\npub enum Role','    pub fn push_user(').replace('    #[cfg(test)]\n    text_work: text_run::TextWork,\n','')+sl(s,'    fn allocate_key(','fn delta_keep(')+sl(s,'/// Whether a row renders the same','\nmod cache;'))
  original=sl(t,'/// Time of a row pushed locally','/// Whether a row renders the same')
  counted=original.replace('.find(|before| {','.find(|before| {\n            #[cfg(feature="visits")] crate::exercise::visit();').replace('while let Some((last, rest)) = old.split_last() {','while let Some((last, rest)) = old.split_last() {\n        #[cfg(feature="visits")] crate::exercise::visit();')
  assert counted!=original
  proj=root/side;src=proj/'src';src.mkdir(parents=True)
  (src/'transcript.rs').write_text(t.replace(original,counted))
  (src/'main.rs').write_text('#![allow(dead_code,unused_imports)]\n'+''.join(f'#[path="../../common/{n}.rs"] mod {n};\n' for n in ['app_protocol','domain','contracts','model_standard','meter','exercise'])+'mod transcript;fn main(){exercise::run();}')
  name=f'desktop-proof-{side}'
  (proj/'Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="0.0.1"\nedition="2024"\n[dependencies]\nserde={{version="=1.0.228",features=["derive"]}}\nserde_json="=1.0.151"\nuuid={{version="=1.23.1",features=["serde"]}}\n[features]\nvisits=[]\n')
  lock=(pkg/'Cargo.lock').read_text();assert lock.count('desktop-proof-stock')==1;(proj/'Cargo.lock').write_text(lock.replace('desktop-proof-stock',name))
  cargo=['cargo']
  if args.vendor: cargo+=['--offline','--config','source.crates-io.replace-with="verified"','--config',f'source.verified.directory="{args.vendor.resolve()}"']
  for mode in ('default','visits'):
   run=subprocess.run(cargo+['run','--locked','--release']+(['--features','visits'] if mode=='visits' else []),cwd=proj,check=True,capture_output=True,text=True,env={**os.environ,'CARGO_TARGET_DIR':str(root/'target')})
   rows=run.stdout.splitlines();assert rows==receipt['results'][side][mode],(side,mode,rows)
   print(side,mode,*rows,sep='\n',flush=True)
