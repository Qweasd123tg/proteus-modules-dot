"""Measure a parser stage, not a GUI. Requires pinned Desktop source, Rust 1.95 / Cargo, locked deps."""
import argparse,os,subprocess,sys,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('desktop',type=Path);p.add_argument('out',type=Path);p.add_argument('--offline',action='store_true');p.add_argument('--cpu',type=int);o=p.parse_args()
here=Path(__file__).resolve().parent
if o.cpu is not None:os.sched_setaffinity(0,{o.cpu})
o.out=o.out.resolve();o.out.mkdir(exist_ok=True,parents=True)
with tempfile.TemporaryDirectory() as tmp:
    wd=Path(tmp)
    subprocess.run([sys.executable,here/'prepare.py',o.desktop.resolve(),wd],check=True)
    for mode,opts in [('timing',[]),('heap',['--features','stats'])]:
        cmd=['cargo','build','--quiet','--locked','--release',*opts]+(['--offline'] if o.offline else [])
        subprocess.run(cmd,cwd=wd,check=True)
        subprocess.run([Path(os.environ.get('CARGO_TARGET_DIR',wd/'target'))/'release/html-dom-probe',here/'cases.jsonl'],stdout=(o.out/(mode+'.jsonl')).open('w'),check=True)
subprocess.run([sys.executable,here/'summarize.py',o.out],check=True)
