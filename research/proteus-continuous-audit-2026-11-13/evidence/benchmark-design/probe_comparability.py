from pathlib import Path
import json, sys, hashlib
ROOT=Path('/workspace/shared/benchmark-design-audit')
HERE=ROOT/'examples/performance/coding-harness'
sys.path.insert(0,str(HERE))
import runner,long_report,corpus
E=Path(__file__).resolve().parent
runs=E/'mixed-effort-runs';runs.mkdir(exist_ok=True)
model='opencode-go/deepseek-v4.1-flash'
case='journal-segments'
fixture={'implementation.py':'a'*64}
for arm,effort in [('pi','high'),('proteus-pi','low')]:
    native=arm=='pi'
    metrics={'model_requests':1,'all_tool_calls':1,'tool_names':{'read':1},
             'provider_usage':{'input_tokens':100,'cached_input_tokens':0,'output_tokens':10},
             'providers':['opencode-go']}
    if native:metrics.update(models=['deepseek-v4.1-flash'],reasoning_efforts=[effort],settled=True,errors=[])
    else:metrics.update(model_refs=[json.dumps({'model':'deepseek-v4.1-flash'})],
                       reasoning_refs=[json.dumps({'effort':effort})],
                       settlements=[{'status':'success','error':None}],model_responses=1)
    result={'agent':'pi' if native else 'proteus','model':model,'reasoning':effort,'returncode':0,
            'timed_out':False,'metrics':metrics,'fixture_files_sha256':fixture,'prompt_sha256':'b'*64,
            'wall_seconds':10,'expected_turns':1}
    runner.check_pipeline(result)
    assert result['pipeline_ok']
    directory=runs/f'flash_{case}_1_{arm}';directory.mkdir(exist_ok=True)
    corpus.write_json(directory/'result.json',result)
    corpus.write_json(directory/'grading.json',{'case':case,'passed':True,'returncode':0,
            'fixture_unchanged':True,'timed_out':False,'output':'1 passed','reference_control':False})
report=long_report.build(runs,[],[case],['pi','proteus-pi'],E/'no-baseline',[])
corpus.write_json(E/'mixed-effort-report.json',report)
long_report.write_markdown(report,E/'mixed-effort-report.md')
observed={'complete':report['complete'],'declared_model':report['model'],'declared_effort':report['effort'],
          'actual_rows':[{k:row[k] for k in ['arm','model','effort','pipeline_ok','pass']} for row in report['rows']],
          'pair':report['pairs'][0]}
print(json.dumps(observed,indent=2))
assert report['complete'] and report['effort']=='high' and report['pairs'][0]['both_graded']
assert {row['effort'] for row in report['rows']}=={'low','high'}
