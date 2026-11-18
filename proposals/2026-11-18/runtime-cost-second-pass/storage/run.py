"""Linux: python run.py /path/to/Proteus-modules > results.json. Same fixture for A/B."""
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BASE = '37b3d9c4db0b8cb5c4ca6cec690ebf7ce64c1979'


def build(checkout, root, target, side):
    src = root / ('src-' + side)
    subprocess.run(['git','clone','-q','--shared','--no-checkout',checkout,src],check=True)
    subprocess.run(['git','checkout','-q','--detach',BASE],cwd=src,check=True)
    if side == 'after':
        subprocess.run(['git','apply','--whitespace=error',HERE/'current-conversation.patch'],cwd=src,check=True)
    examples = src / 'storage/session-storage/examples'
    examples.mkdir(exist_ok=True)
    shutil.copyfile(HERE/'service_probe.rs',examples/'dot_current_conversation.rs')
    subprocess.run(['cargo','build','--locked','-p','session-storage','--release','--example','dot_current_conversation'],
                   cwd=src,check=True,env=dict(os.environ,CARGO_TARGET_DIR=str(target)))
    return shutil.copy2(target/'release/examples/dot_current_conversation',root/side)


def run(checkout):
    with tempfile.TemporaryDirectory() as t:
        work = Path(t)
        target = Path(os.environ.get('CARGO_TARGET_DIR',work/'target')).resolve()
        bins = {s:build(checkout,work,target,s) for s in ['before','after']}
        out = dict(revision=BASE, rustc=subprocess.check_output(['rustc','-V'],text=True).strip(), profile='release')
        def call(side,mode,location,n,size):
            return subprocess.check_output([bins[side],mode,location,str(n),str(size)],text=True)
        for name,n,size in [('empty',0,0),('short',8,256),('long',128,131072)]:
            location = work/name
            call('before','seed',location,n,size)
            if n:
                errors=[json.loads(call(s,'error',location,n,size)) for s in bins]
                assert errors[0]==errors[1]
            data = {s:[] for s in bins}
            for i in range(11):
                for side in (['before','after'] if i%2==0 else ['after','before']):
                    row=json.loads(call(side,'read',location,n,size))
                    if i:
                        data[side].append(row)
            out[name] = dict(records=n, text_bytes_per_message=size+9, samples=data,
                             median={s:{k:statistics.median(x[k] for x in records)
                                        for k in ['ns','rss_kib']} for s,records in data.items()},
                             corrupted_first_record=(errors[0]['error'] if n else None))
        print(json.dumps(out,indent=2))


if __name__=='__main__':
    run(Path(sys.argv[1]).resolve())
