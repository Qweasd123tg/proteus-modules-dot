"""Reconstruct the complete authored demonstration, including typed-record hashes.

Random instance/cwd/call IDs are validated and correlated, never authenticated.
This is not a Core approval, journal, official-reader or truth certificate.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
spec=importlib.util.spec_from_file_location('gate_common',Path(__file__).with_name('gate_common.py'));g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
KEY='proteus.example.correction_cas'
ARTIFACT=b'channel=draft\npublish=false\n'

def sha(data):return hashlib.sha256(data).hexdigest()
def digest(value):return sha(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode())
def spans_config():return {'schema_version':1,'sources':[{'id':'release','path':'evidence/release.txt'}]}
def policy():return {'schema_version':1,'store_id':'release-proposals','database_path':'store/notes.sqlite','evidence_policy':{'verifier_tool':'evidence.verify_spans','expected_config_sha256':digest(spans_config()),'sources':[{'source_id':'release','path':'evidence/release.txt'}]}}

def evidence(which):
    start,quote=(0,'channel=draft') if which=='channel' else (14,'publish=false')
    return {'source_id':'release','expected_sha256':sha(ARTIFACT),'claims':[{'claim_id':which,'start_byte':start,'end_byte':start+len(quote),'quote':quote}]}

def toolcall(call_id,name,args):return {'id':call_id,'name':name,'args':args,'surface':'function','raw_arguments':None}
def response(kind,value,replayed=False):return {'call_id':'fixture-outer','ok':True,'output':f'Correction memory: {kind}. Stored text is a proposal, not a verified fact.','content':[],'error':None,'metadata':{KEY:{'kind':kind,'result':value,'audit':{'replayed':replayed,'semantic_entailment':'not_evaluated','grants_write_authority':False}}}}

def record(identity,which,ids,index):
    proof=evidence(which);claim=proof['claims'][0]
    proposal={**identity,'key':'release.status','expected_revision':0,'new_text':'Release remains draft.' if which=='channel' else 'Do not publish this release.','evidence':proof}
    request={'operation_id':'op-'+which,'proposal':proposal}
    observation={'schema_version':1,'status':'exact_byte_match','scope':'observed_host_read_bytes','source_id':'release','configured_path':'evidence/release.txt','observed_path':identity['workspace_cwd']+'/evidence/release.txt','config_sha256':digest(spans_config()),'content_sha256':sha(ARTIFACT),'source_bytes':len(ARTIFACT),'verifier_call_id':ids[index],'reader_call_id':ids[index+1],'verified_claims':[{'claim_id':which,'start_byte':claim['start_byte'],'end_byte':claim['end_byte'],'quote_sha256':sha(claim['quote'].encode())}],'origin_verified':False,'semantic_entailment':'not_evaluated'}
    outcome={k:identity[k] for k in ('schema_version','store_id','database_instance_id','workspace_cwd','database_path')}
    outcome.update(operation_id='op-'+which,request_sha256=digest(request),key='release.status',expected_revision=0,observed_revision=0 if which=='channel' else 1,decision='applied' if which=='channel' else 'conflict',resulting_revision=1 if which=='channel' else None,proposal_sha256=digest(proposal),evidence_observation_sha256=digest(observation))
    return {'request':request,'outcome':outcome,'observation':observation}

def expected(identity,ids):
    a=record(identity,'channel',ids,4);b=record(identity,'publish',ids,6)
    trace=[]
    for index,which in enumerate(('channel','publish','channel','publish')):
        trace.extend([toolcall(ids[2*index],'evidence.verify_spans',evidence(which)),toolcall(ids[2*index+1],'read_file',{'path':'evidence/release.txt'})])
    return {'fixture_kind':'actual_modules_authored_callbacks_owned_artifact','actual_core':False,'host_approval_exercised':False,
            'init':response('initialized',identity),'applied':response('operation',a),'conflict':response('operation',b),'replay':response('operation',a,True),
            'changed_payload_rejected':{'call_id':'fixture-outer','ok':False,'output':'','content':[],'error':'correction_memory: operation_payload_mismatch','metadata':None},
            'current':response('read',{'identity':identity,'key':'release.status','revision':1,'record':a}),'nested_calls':trace}

def verify(report):
    raw=report['init']['metadata'][KEY]['result']
    fields=('schema_version','store_id','database_instance_id','workspace_cwd','database_path','policy_sha256')
    g.require(set(raw)==set(fields),'identity shape');identity={k:raw[k] for k in fields}
    g.require(g.exact(identity['schema_version'],1) and identity['store_id']=='release-proposals' and identity['database_path']=='store/notes.sqlite','fixture store identity')
    g.require(type(identity['database_instance_id']) is str and re.fullmatch('[a-f0-9]{32}',identity['database_instance_id']),'instance identity')
    cwd=identity['workspace_cwd'];g.require(type(cwd) is str and cwd.startswith('/') and len(cwd)<=4096 and not cwd.endswith('/') and all(ord(c)>=32 for c in cwd),'fixture cwd')
    g.require(identity['policy_sha256']==digest(policy()),'policy digest')
    calls=report['nested_calls'];g.require(type(calls) is list and len(calls)==8,'eight nested calls')
    ids=[call['id'] for call in calls]
    g.require(all(type(x) is str and 0<len(x)<=128 and x!='fixture-outer' and all(ord(c)>=32 for c in x) for x in ids) and len(set(ids))==8,'distinct bounded callback identities')
    g.require(g.exact(report,expected(identity,ids)),'exact typed authored workflow report')
    return {'status':'passed','applied_revision':1,'durable_conflict':True,'same_payload_replay':True,'changed_payload_refused':True,'nested_calls':8,'scope':'actual modules; authored callbacks and temporary artifact; no Core authorization or semantic truth'}
