#!/usr/bin/env python3
"""Fixed scoped locked runtime gates under the outer sampled/deadline envelope."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
workspace=Path('examples/correction-memory');artifacts=Path('validation/correction-memory');ci=workspace/'ci'
spec=importlib.util.spec_from_file_location('contract',ci/'contract.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
commands=[]

def save(path,data):path.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')

def run(label,argv):
    commands.append({'label':label,'argv':argv,'returncode':None});save(artifacts/'commands.json',commands)
    with (artifacts/(label+'.stdout')).open('xb') as out,(artifacts/(label+'.stderr')).open('xb') as err:
        result=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
    commands[-1]['returncode']=result.returncode;save(artifacts/'commands.json',commands)
    if result.returncode:raise RuntimeError('stage failed: '+label)

def main():
    artifacts.mkdir(parents=True,exist_ok=False);save(artifacts/'source-before.json',c.source_identity(workspace))
    try:
        for label,argv in c.plan(workspace):
            if label=='test-actual_modules':save(artifacts/'binaries-before.json',c.binary_identity())
            run(label,argv)
        save(artifacts/'binaries-after.json',c.binary_identity())
    finally:save(artifacts/'source-after.json',c.source_identity(workspace))
    subprocess.run([sys.executable,'-B','-I',str(ci/'verify_runtime.py'),str(workspace),str(artifacts)],check=True)
if __name__=='__main__':main()
