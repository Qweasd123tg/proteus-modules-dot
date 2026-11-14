#!/usr/bin/env python3
"""Offline artifact-level reproductions against unmodified Core benchmark helpers."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

REPO = Path('/workspace/shared/testing-fidelity-audit')
HERE = REPO/'examples/performance/coding-harness'
sys.path.insert(0, str(HERE))
import adapters
import runner
import report
import long_report


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))


def pi_message(usage='absent', **extra):
    message = {'role':'assistant', 'model':'fixture', 'provider':'openai-codex', 'stopReason':'stop', 'content':[], **extra}
    if usage != 'absent':
        message['usage'] = usage
    return {'type':'message_end', 'message':message}


def pi_fixture(path, events):
    write_rows(path/'stdout.jsonl', events)
    write_rows(path/'runtime/pi-sessions/session.jsonl', [{'type':'thinking_level_change', 'thinkingLevel':'high'}])


def gate(agent, metrics):
    result = {'agent':agent, 'model':'fixture', 'reasoning':'high', 'returncode':0, 'timed_out':False, 'metrics':metrics}
    runner.check_pipeline(result)
    return result['pipeline_ok']


with tempfile.TemporaryDirectory(prefix='proteus-accounting-') as temp:
    root = Path(temp)
    full = {'input':10, 'cacheRead':100, 'cacheWrite':0, 'output':5, 'reasoning':2}
    output = root/'missing-pi'
    pi_fixture(output, [pi_message(full), pi_message(), {'type':'agent_end'}])
    pi = adapters.metrics('pi', output)
    assert pi['model_requests'] == 2 and pi['provider_usage']['input_tokens'] == 110
    assert gate('pi', pi)
    missing_pi = {'assistant_replies':2, 'replies_with_usage':1, 'pipeline_ok':gate('pi',pi), 'actual_reported_totals':pi['provider_usage'], 'expected_complete_input_tokens':None}

    output = root/'missing-codex'
    write_rows(output/'stdout.jsonl', [
        {'type':'turn.completed','usage':{'input_tokens':110,'cached_input_tokens':100,'output_tokens':5}},
        {'type':'turn.completed'}])
    write_rows(output/'runtime/home/.codex/sessions/session.jsonl', [{'type':'turn_context','payload':{'model':'fixture','effort':'high'}}])
    codex = adapters.metrics('codex',output)
    assert codex['provider_usage']['input_tokens'] == 110
    missing_codex = {'completed_turns':2, 'turns_with_usage':1, 'actual_reported_totals':codex['provider_usage'], 'expected_complete_input_tokens':None}

    output = root/'truncated-pi'
    pi_fixture(output, [pi_message(full,stopReason='length',content=[{'type':'text','text':'Incomplete final answer...'}]), {'type':'agent_end','willRetry':False}])
    truncated_metrics = adapters.metrics('pi',output)
    truncated_report = {'agent':'pi','model':'fixture','reasoning':'high','returncode':0,'timed_out':False,'metrics':truncated_metrics}
    runner.check_pipeline(truncated_report)
    assert truncated_report['pipeline_ok'] is True
    truncated = {'final_stop_reason':'length','pipeline_ok':truncated_report['pipeline_ok'],
                 'errors':truncated_metrics['errors'],
                 'usage_complete':long_report.usage_completion(output,truncated_report,truncated_metrics)[0],
                 'taxonomy_with_passing_grader':long_report.failure_taxonomy(truncated_report,{'passed':True},truncated_metrics['errors'])}

    # Historical native Pi timeout: long report already identifies this usage as partial.
    saved = json.loads((REPO/'examples/performance/results/2026-11-11-deepseek-long.json').read_text())
    old = next(row for row in saved['rows'] if row['case']=='journal-segments' and row['arm']=='pi' and row['attempt']==1)
    run = root/'matrix/flash_journal-segments_1_pi'
    run.mkdir(parents=True)
    result = {'agent':'pi','model':old['model'],'reasoning':old['effort'],'pipeline_ok':False,
              'timed_out':True,'returncode':-15,'wall_seconds':old['seconds'],'prompt_sha256':old['prompt_sha256'],
              'fixture_files_sha256':{},'metrics':{'provider_usage':old['reported_usage'],
              'model_requests':old['requests'],'all_tool_calls':old['actions'],'tool_names':old['tools']}}
    (run/'result.json').write_text(json.dumps(result))
    (run/'grading.json').write_text(json.dumps({'passed':False}))
    short = report.summarize(report.read_rows([run.parent],[]))[0]
    assert old['tokens']['input_tokens'] is None and short['input']==1400843
    partial = {'historical_case':old['case'],'timed_out':True,'long_report_usage_complete':old['usage_complete'],
               'long_report_complete_input_tokens':old['tokens']['input_tokens'],'long_report_partial_input':old['observed_partial_usage']['input_tokens'],
               'short_report_complete_input':short['input'],'short_report_complete_output':short['output'],
               'short_report_has_completeness_flag':any('partial' in k or 'complete' in k or 'bound' in k for k in short)}

    # Compare recovered provider-error treatment using each genuine metrics adapter.
    output = root/'retry-pi'
    pi_fixture(output,[pi_message({k:0 for k in full},stopReason='error',errorMessage='503 Service Unavailable'),
                      {'type':'agent_end','willRetry':True},
                      {'type':'auto_retry_start','attempt':1,'maxAttempts':3,'delayMs':2000,'errorMessage':'503 Service Unavailable'},
                      pi_message(full), {'type':'auto_retry_end','success':True,'attempt':1},
                      {'type':'agent_end','willRetry':False}, {'type':'agent_settled','aborted':False}])
    pi_retry = adapters.metrics('pi',output)
    output = root/'retry-proteus'
    journal = output/'runtime/sessions/one/journal.jsonl'
    rows = []
    def record(kind, payload):
        rows.append({'schema_version':21,'session_seq':len(rows)+1,'timestamp_ms':1000+len(rows),
                     'session_id':'session','turn_id':'turn','kind':kind,'payload':{'storage':'inline','value':payload}})
    request = {'model':{'provider':'chatgpt','model':'fixture'},'reasoning':{'effort':'high'},'tools':[],'messages':[]}
    record('turn_opened',{})
    record('model_request_recorded',{'exchange_id':'first','origin':'direct','request':request})
    record('model_response_recorded',{'exchange_id':'first','outcome':{'status':'failure','failure':{'message':'503 Service Unavailable'}}})
    record('model_request_recorded',{'exchange_id':'retry','origin':'direct','request':request})
    record('model_response_recorded',{'exchange_id':'retry','outcome':{'status':'response','response':{'messages':[],'usage':{'input_tokens':110,'cached_input_tokens':100,'output_tokens':5}}}})
    record('turn_settled',{'status':'success','error':None})
    write_rows(journal,rows)
    proteus_retry = adapters.metrics('proteus',output)
    assert not gate('pi',pi_retry) and gate('proteus',proteus_retry)
    retry = {'native_pi_pipeline_ok':gate('pi',pi_retry),'proteus_pipeline_ok':gate('proteus',proteus_retry),
             'native_pi_settled':pi_retry['settled'],'proteus_settlements':proteus_retry['settlements'],
             'native_pi_errors':pi_retry['errors'],'proteus_failures':proteus_retry['failures'],
             'scope':'Synthetic completed retry artifacts; no live native retry run performed.'}

print(json.dumps({'native_pi_truncation':truncated,'missing_pi_usage':missing_pi,'missing_codex_usage':missing_codex,'partial_timeout_totals':partial,'retry_asymmetry':retry},indent=2))
