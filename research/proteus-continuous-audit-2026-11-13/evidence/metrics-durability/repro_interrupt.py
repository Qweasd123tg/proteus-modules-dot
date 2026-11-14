"""Interrupt an owned synthetic benchmark runner after committed model metrics.
The actual runner, extraction module, bubblewrap and SIGINT path are exercised.
"""
from pathlib import Path
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

EVIDENCE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('partial_export_repro',EVIDENCE/'repro_partial_export.py')
previous=importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
HARNESS=previous.HARNESS
WORKER=previous.WORKER.split('# Affect only this synthetic subprocess.')[0]+'''
Path('/state/ready').write_text('committed 30 input tokens; 1 tool')
import time
while True:
    time.sleep(10)
'''
DRIVER='''
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, {harness!r})
import runner, adapters
root=Path({root!r})
def prepare(args,runtime):
    (runtime/'home').mkdir()
    (runtime/'native').mkdir()
    (runtime/'native/registry.json').write_text('{{}}')
    return ['/usr/bin/python3','/workspace/worker.py'], [(Path({harness!r})/'open_code_native.py','/runtime/open_code_native.py')]
sys.argv=['runner.py','--agent','opencode','--case-dir',str(root/'case'),'--output',str(root/'output'),'--binary','/usr/bin/python3','--model','openai/fixture-model','--reasoning','high','--timeout','10']
with patch.object(adapters,'prepare',side_effect=prepare):
    raise SystemExit(runner.main())
'''


def run_case(root, interrupt):
    case=root/'case'; (case/'repo').mkdir(parents=True)
    (case/'repo/worker.py').write_text(WORKER)
    (case/'prompt.txt').write_text('synthetic metrics interrupt test\n')
    driver=root/'driver.py'; driver.write_text(DRIVER.format(harness=str(HARNESS),root=str(root)))
    with (root/'driver-stdout.log').open('w') as out, (root/'driver-stderr.log').open('w') as err:
        process=subprocess.Popen([sys.executable,'-B',str(driver)],stdout=out,stderr=err,start_new_session=True)
        try:
            deadline=time.monotonic()+5
            while not (root/'output/runtime/ready').exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('worker failed to become ready')
                time.sleep(.01)
            children_path=Path(f'/proc/{process.pid}/task/{process.pid}/children')
            inventory_available=children_path.exists()
            children=[int(x) for x in children_path.read_text().split()] if inventory_available else []
            if interrupt:
                process.send_signal(signal.SIGINT)
            code=process.wait(timeout=15)
        finally:
            if process.poll() is None:
                process.kill(); process.wait()
    output=root/'output'
    result_path=output/'result.json'
    report=json.loads(result_path.read_text()) if result_path.exists() else None
    imported=importlib.util.spec_from_file_location('interrupt_long_report',HARNESS/'long_report.py')
    module=importlib.util.module_from_spec(imported); imported.loader.exec_module(module)
    trial=module.read_trial(output,'go-review','opencode',1)
    expected=json.loads((output/'runtime/fresh-snapshot-control/usage.json').read_text())
    return dict(exit_code=code, result_saved=report is not None,
                native_usage_saved=(output/'runtime/native/usage.json').is_file(),
                database_removed=not(output/'runtime/home/.local/share/opencode/opencode.db').exists(),
                expected_input=expected['sessions'][0]['tokens_input'],
                observed_input=report.get('metrics',{}).get('provider_usage',{}).get('input_tokens') if report else None,
                expected_actions=sum(len(m['tools']) for m in expected['assistant_messages']),
                observed_actions=report.get('metrics',{}).get('all_tool_calls') if report else None,
                long_report_state=trial['state'], process_inventory_available=inventory_available, bwrap_children=children,
                bwrap_children_still_non_zombie=[pid for pid in children if Path(f'/proc/{pid}/stat').exists() and Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0] not in ('Z','X')])

if __name__=='__main__':
    root=Path(tempfile.mkdtemp(prefix='interrupt-runs-',dir=EVIDENCE))
    interrupted=run_case(root/'sigint',True)
    control=run_case(root/'deadline-control',False)
    result=dict(head='89997df995df7c39b713e16aba216ecb19c8f497',root=str(root),interrupted=interrupted,deadline_control=control)
    (EVIDENCE/'interrupt-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    assert not interrupted['result_saved'] and not interrupted['native_usage_saved']
    assert interrupted['database_removed'] and interrupted['long_report_state']=='running'
    assert control['result_saved'] and control['native_usage_saved'] and control['observed_input']==30 and control['observed_actions']==1
