#!/usr/bin/env python3
"""Exact authored append-group artifact gate; not independent Core execution."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import uuid

SPEC=importlib.util.spec_from_file_location('group_runner',Path(__file__).resolve().parents[1]/'run_group_probe.py')
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)
PIN=runner.PIN
require,same=runner.require,runner.same


def verify_control_log(text, expected):
    require(type(expected) is list and all(type(name) is str for name in expected) and len(expected)==len(set(expected)), 'invalid expected control names')
    actual=[]
    for line in text.splitlines():
        if not line.startswith('test_'):continue
        match=re.fullmatch(r'(test_\w+) \(__main__\.([A-Za-z_]\w*)\.\1\) \.\.\. ok',line)
        require(match is not None,'malformed/nonpassing named control')
        actual.append(match.group(2)+'.'+match.group(1))
    require(len(actual)==len(set(actual)) and sorted(actual)==sorted(expected),'named control suite differs')
    require(re.findall(r'^Ran (\d+) tests? in [^\n]+$',text,re.M)==[str(len(expected))] and text.rstrip().endswith('\nOK'),'missing exact control success summary')


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def pairs(items):
    value={}
    for key,item in items:
        require(key not in value,'duplicate JSON key: '+key);value[key]=item
    return value


def document(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 8*1024**2,'invalid bounded evidence file')
    def constant(value):raise ValueError('nonfinite JSON number: '+value)
    return json.loads(path.read_text(),object_pairs_hook=pairs,parse_constant=constant)


def expected_corpus():
    # Independent literal construction of this one authored DTO shape, not a
    # generic alternative Core parser or validator.
    return [{'id':str(uuid.UUID(int=0x11111111111141118111000000000000+index)),
             'role':'User','phase':None,'parts':[{'part_id':str(uuid.UUID(int=0x22222222222242228222000000000000+index)),
             'provenance':'user','scope':'conversation','payload':{'Text':{'text':f'{index:04}:'+251*'x'}}}],
             'name':None,'tool_call_id':None,'metadata':None} for index in range(256)]


def checks():
    result={'generate':('generate',256,None)}
    result['pilot-64-b8']=('run',64,8);result['pilot-64-b8-reopen']=('reopen',64,8)
    for kind in ['active','incoming']:result['rollback-'+kind]=('rollback',kind,None)
    for batch in [1,8,64,256]:
        for repeat in range(1,4):
            name=f'batch-{batch}-r{repeat}'
            result[name]=('run',256,batch);result[name+'-reopen']=('reopen',256,batch)
    return result


def check_journal(path,groups):
    require(path.stat().st_size <= 8*1024**2,'journal exceeds evidence bound')
    lines=path.read_bytes().splitlines()
    require(len(lines)==len(groups),'wrong independent journal line count')
    ids=set()
    for index,(line,group) in enumerate(zip(lines,groups),1):
        record=json.loads(line,object_pairs_hook=pairs)
        require(same(record.get('schema_version'),21) and same(record.get('session_seq'),index),'wrong journal schema/sequence')
        require(record.get('kind')=='history_mutated' and record.get('execution_id') is None and record.get('turn_id') is None,'unexpected journal fact/authority')
        record_id=record.get('record_id');require(type(record_id) is str and record_id not in ids,'duplicate/missing record id');ids.add(record_id)
        payload=record.get('payload',{});require(payload.get('storage')=='inline','independent journal blob confound')
        value=payload.get('value',{})
        require(same(value.get('previous_revision'),index-1) and same(value.get('new_revision'),index),'wrong independent group revision')
        require(value.get('mutation')=='append' and value.get('compaction') is None and same(value.get('tool_results'),[]),'unexpected history mutation scope')
        require(same(value.get('messages'),group),'independent exact stored message group mismatch')


def validate_summary(result,env,processes,outputs):
    require(result.get('status')=='passed' and result.get('core_pin')==PIN,'stage did not pass at expected pin')
    expected=checks();items=result.get('checks',[])
    names=[item.get('name') for item in items]
    require(len(names)==len(set(names))==29 and set(names)==set(expected),'incomplete or duplicate child coverage')
    require(result.get('source_and_binary_unchanged') is True and same(env.get('source_and_binary_hashes_before'),result.get('source_and_binary_hashes_after')),'source/binary input changed')
    require(result.get('corpus_unchanged') is True,'shared corpus changed')
    by_name={item['name']:item.get('value') for item in items}
    summaries=[]
    for name,(command,count,batch) in expected.items():
        value=by_name[name]
        require(type(value) is dict and same(outputs.get(name),value),'stdout/result mismatch')
        require(value.get('core_pin')==PIN,'wrong child pin')
        process=processes.get(name,{})
        require(type(process.get('returncode')) is int and process.get('returncode')==0,'child failed')
        require(process.get('new_process_group') is True and process.get('timed_out') is False and process.get('drain_timed_out') is False and process.get('cleanup_error') is None and process.get('oversized_output') is False,'child bounds/cleanup failed')
        if command=='run':
            summary=runner.validate_workload(value,count,batch)
            if count==256:summaries.append((name,summary))
        elif command=='reopen':
            require(value.get('event')=='reopen' and value.get('journal_unchanged') is True and same(value.get('messages'),count) and same(value.get('batch_size'),batch),'wrong fresh-reopen control')
            runner.validate_projection(value.get('validation',{}),count,batch)
            require(same(value['validation'],by_name[name.removesuffix('-reopen')]['validation']),'reopen projection mismatch')
        elif command=='rollback':runner.validate_rollback(value,count)
        else:
            require(value.get('event')=='corpus' and same(value.get('messages'),256) and same(value.get('message_text_bytes'),256) and value.get('deterministic_ids_and_values') is True,'wrong corpus generator control')
    workloads=result.get('workloads',[])
    require(len(workloads)==12 and {item.get('name') for item in workloads}=={name for name,_ in summaries},'incomplete workload summary')
    for name,computed in summaries:
        row=next(item for item in workloads if item['name']==name)
        for key,value in computed.items():require(same(row.get(key),value),'derived workload total mismatch')
    return by_name


def verify(directory,package,binary,expected_receipt):
    require(digest(package/'SOURCE-RECEIPT.json')==expected_receipt,'unreviewed source receipt')
    receipt=document(package/'SOURCE-RECEIPT.json')
    require(receipt.get('core_pin')==PIN,'wrong receipt pin')
    names=[item['path'] for item in receipt['files']]
    require(len(names)==len(set(names)),'duplicate source receipt path')
    for item in receipt['files']:
        name=Path(item['path']);require(not name.is_absolute() and '..' not in name.parts,'invalid source inventory path')
        path=package/name
        require(same(path.stat().st_size,item['bytes']) and digest(path)==item['sha256'],'reviewed source bytes changed')
    result,env=document(directory/'result.json'),document(directory/'environment.json')
    expected_limits={'child_wall_seconds':60,'child_cpu_seconds':30,'child_address_space_bytes':512*1024**2,'max_child_file_bytes':8*1024**2,'disk_reserve_bytes':1024**3}
    require(env.get('core_pin')==PIN and same(env.get('limits'),expected_limits),'wrong pin/resource limits')
    environment={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    for key,leaf in [('HOME','home'),('XDG_CONFIG_HOME','xdg-config'),('XDG_CACHE_HOME','xdg-cache'),('XDG_DATA_HOME','xdg-data'),('TMPDIR','tmp')]:environment[key]=str(directory/leaf)
    require(same(env.get('isolated_child_environment'),environment),'unexpected child environment')
    paths=[binary,package/'Cargo.toml',package/'Cargo.lock',package/'run_group_probe.py',package/'src/allocation.rs',package/'src/main.rs']
    hashes={str(path):digest(path) for path in paths}
    require(same(env.get('source_and_binary_hashes_before'),hashes),'current input bytes differ')
    expected=checks()
    processes={name:document(directory/(name+'.process.json')) for name in expected}
    outputs={name:document(directory/(name+'.stdout.json')) for name in expected}
    values=validate_summary(result,env,processes,outputs)
    corpus_path=directory/'corpus.json';corpus=document(corpus_path)
    require(corpus_path.stat().st_size<=2*1024**2 and same(corpus,expected_corpus()),'deterministic corpus content/IDs mismatch')
    require(digest(corpus_path)==result.get('corpus_sha256') and same(corpus_path.stat().st_size,values['generate'].get('corpus_bytes')),'corpus hash/size mismatch')
    for name,(command,count,batch) in expected.items():
        if command=='generate':args=['generate',str(corpus_path)]
        elif command=='rollback':
            root=directory/('dataset-'+name);session=Path(values[name]['session_dir'])
            require(session.is_absolute() and session.is_relative_to(root),'rollback session escaped owned root')
            args=['rollback',str(root),str(corpus_path),count]
            before,after=root/'before-rejection.journal.jsonl',root/'after-rejection.journal.jsonl'
            require(before.stat().st_size<=8*1024**2 and before.read_bytes()==after.read_bytes(),'rollback evidence bytes changed')
            check_journal(before,[corpus[:1]])
            check_journal(session/'journal.jsonl',[corpus[:1],corpus[1:3]])
        else:
            base=name.removesuffix('-reopen');root=directory/('dataset-'+base)
            session=Path(values[base]['session_dir'])
            require(session.is_absolute() and session.is_relative_to(root),'workload session escaped owned root')
            args=[command,str(root if command=='run' else session),str(corpus_path),str(count),str(batch)]
            if command=='run':
                history=root/'final-history.json'
                require(values[name].get('final_history_file')==str(history) and same(document(history),corpus[:count]),'final canonical history mismatch')
                if count==256:require(digest(history)==digest(corpus_path),'final-history bytes differ')
                check_journal(session/'journal.jsonl',[corpus[index:index+batch] for index in range(0,count,batch)])
                if count==256:
                    row=next(item for item in result['workloads'] if item['name']==name)
                    require(row.get('final_history_sha256')==digest(history) and row.get('journal_sha256')==digest(session/'journal.jsonl'),'workload file hash mismatch')
        require(same(processes[name].get('command'),[str(binary),*args]),'child argv differs from exact owned fixture')
    return {'status':'verified','core_pin':PIN,'required_children':29,'actual_workload_children':12,'fresh_workload_reopens':12,
            'pilot_and_reopen':2,'whole_group_rollback_cases':2,'corpus_generator':1,
            'deterministic_final_values_and_inline_groups_checked':True,'rollback_bytes_independently_checked':True,
            'transaction_boundaries_differ':True,'source_receipt_sha256':expected_receipt,
            'scope':'receipt/journal inspection for our fixed append fixture, not independent Core execution/general validator/security boundary or speedup proof'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True,type=Path);parser.add_argument('--package',required=True,type=Path);parser.add_argument('--binary',required=True,type=Path);parser.add_argument('--expected-receipt',required=True)
    args=parser.parse_args();print(json.dumps(verify(args.directory.resolve(strict=True),args.package.resolve(strict=True),args.binary.resolve(strict=True),args.expected_receipt),indent=2))


if __name__=='__main__':main()
