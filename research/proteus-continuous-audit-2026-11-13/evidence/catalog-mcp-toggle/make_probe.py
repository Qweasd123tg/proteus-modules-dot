from pathlib import Path
import json,subprocess,hashlib,argparse
R=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--desktop',type=Path,default=Path('/workspace/scratch/3ba0fff8d310/desktop-behaviour'))
parser.add_argument('--core',type=Path,default=Path('/workspace/shared/proteus-review-20261112/core'))
a=parser.parse_args();D=a.desktop.resolve();C=a.core.resolve()
S=R/'probe/src';S.mkdir(parents=True,exist_ok=True);hashes={}
def source(p):
 b=subprocess.check_output(['git','show','HEAD:'+p],cwd=D);hashes[p]=hashlib.sha256(b).hexdigest();return b.decode()
def write(p,s):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s)
for p in ['src/settings/draft.rs','src/settings/addons.rs','src/settings/mcp.rs','src/packages.rs','src/catalog/schema.rs','src/catalog/skills.rs','src/catalog/open.rs','src/catalog/install.rs','src/catalog/install/plugin.rs']:
 write(S/p.removeprefix('src/'),source(p))
install=S/'catalog/install.rs'; install.write_text(install.read_text().replace('mod component;', 'mod component {pub(super) fn prepare(_: &super::Locations, _: &super::Entry, _: &crate::packages::Contents)->anyhow::Result<super::Target>{anyhow::bail!("unused process component edge")}}'))
mod=source('src/catalog/mod.rs');types=mod[mod.index('use std::path::PathBuf;'):mod.index('impl Locations {')]
write(S/'catalog/mod.rs','pub mod schema; pub mod skills; pub mod open; pub mod install;\n'+types+'''
pub mod build {
 pub fn prepare(_: &super::Locations,_:&super::Source,_:&super::schema::Catalog,_:&super::schema::Entry)->anyhow::Result<crate::packages::Contents>{anyhow::bail!("unused source-build edge")}
}
''')
write(R/'probe/Cargo.toml',f'''[package]
name="catalog-mcp-toggle-probe"
version="0.0.0"
edition="2024"
[workspace]
[dependencies]
proteus-contracts={{path="{C}/crates/proteus-contracts"}}
anyhow="1"
serde={{version="1",features=["derive"]}}
serde_json="1"
serde_yaml="0.9"
uuid={{version="1",features=["v4"]}}
zip={{version="2",default-features=false,features=["deflate"]}}
''')
write(S/'lib.rs','''#![allow(dead_code,unused_imports)]
pub mod packages;
pub mod catalog;
pub mod settings {pub mod draft;pub mod addons;pub mod mcp;pub use draft::Draft;}
pub mod declarative {pub mod manifest {
 pub struct Manifest {pub id:String}
 pub fn parse(_: &str)->anyhow::Result<Manifest>{anyhow::bail!("unused extension edge")}
 pub fn load(_: &std::path::Path)->anyhow::Result<Manifest>{anyhow::bail!("unused extension edge")}
}}
''')
for p in ['src/ui/settings/catalog/apply.rs','src/ui/settings/mcp.rs']:
 source(p)
(R/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
