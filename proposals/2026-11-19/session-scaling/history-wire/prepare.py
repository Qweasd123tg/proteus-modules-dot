"""Prepare headless harness from pinned clean checkouts. No writes to input sources.
Usage: python3 prepare.py CORE_SRC DESKTOP_SRC NEW_WORK_DIR
Then follow README for Cargo commands. Internet or an offline cache of the lockfiles is required.
"""
from pathlib import Path
import shutil,subprocess,sys
src_core=Path(sys.argv[1]).resolve(); desktop=Path(sys.argv[2]).resolve(); work=Path(sys.argv[3]).resolve()
work.mkdir(exist_ok=False); here=Path(__file__).resolve().parent
def get(src,sha):
 d=work/src.name
 if d.exists():raise ValueError(str(d))
 subprocess.run(['git','clone','--no-hardlinks','--quiet','--no-checkout',str(src),str(d)],check=True)
 subprocess.run(['git','-C',str(d),'checkout','--quiet','--detach',sha],check=True)
 return d
core=get(src_core,'8ea2cdaf4195ae24e941354f68d4e97335d139d7')
desktop_pinned=get(desktop,'210cc9f274ffe40533b390a0d9e940f251a9fa22')
target=core/'crates/proteus-core/src/app_server/http/tests/session_reads.rs'
with target.open('ab') as f:f.write(b'\n'+(here/'probe.rs').read_bytes())
client=work/'client'; (client/'src').mkdir(parents=True)
for source in ['api','startup_trace.rs']:
 a=desktop_pinned/'src'/source; b=client/'src'/source
 shutil.copytree(a,b) if a.is_dir() else shutil.copyfile(a,b)
shutil.copytree(desktop_pinned/'crates/client-common',client/'client-common')
shutil.copyfile(here/'client_main.rs',client/'src/main.rs')
shutil.copyfile(here/'client.Cargo.toml',client/'Cargo.toml')
shutil.copyfile(desktop_pinned/'Cargo.lock',client/'Cargo.lock')
print(f"Prepared Core at {core} and no-window Desktop client at {client}")
