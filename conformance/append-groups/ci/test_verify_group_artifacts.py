"""Synthetic gate tests only: no compiled Core, subprocess, external data or tracer."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
v=module('group_gate',Path(__file__).with_name('verify_group_artifacts.py'))
f=module('semantic_fixtures',BASE/'test_group_controls.py')


def fixture():
    values={};processes={}
    for name,(command,count,batch) in v.checks().items():
        if command=='run':value=f.workload(count,batch)
        elif command=='rollback':value=f.rollback(count)
        elif command=='reopen':value={'event':'reopen','core_pin':v.PIN,'messages':count,'batch_size':batch,'journal_unchanged':True,'validation':copy.deepcopy(values[name.removesuffix('-reopen')]['validation'])}
        else:value={'event':'corpus','core_pin':v.PIN,'messages':256,'message_text_bytes':256,'deterministic_ids_and_values':True,'corpus_bytes':1}
        values[name]=value
        processes[name]={'returncode':0,'new_process_group':True,'timed_out':False,'drain_timed_out':False,'cleanup_error':None,'oversized_output':False}
    hashes={'synthetic':'a'*64}
    rows=[]
    for name,(command,count,batch) in v.checks().items():
        if command=='run' and count==256:rows.append({'name':name,**v.runner.validate_workload(values[name],count,batch)})
    result={'status':'passed','core_pin':v.PIN,'checks':[{'name':name,'value':copy.deepcopy(value)} for name,value in values.items()],
            'source_and_binary_unchanged':True,'source_and_binary_hashes_after':hashes,'corpus_unchanged':True,'workloads':rows}
    return [result,{'source_and_binary_hashes_before':copy.deepcopy(hashes)},processes,values]


def change(data,name,key,value):
    data[3][name][key]=copy.deepcopy(value)
    next(item for item in data[0]['checks'] if item['name']==name)['value'][key]=copy.deepcopy(value)


def records(groups):
    return [{'schema_version':21,'record_id':f'authored-record-{index}','session_seq':index,'execution_id':None,'turn_id':None,'kind':'history_mutated',
             'payload':{'storage':'inline','value':{'previous_revision':index-1,'new_revision':index,'mutation':'append','messages':group,'compaction':None,'tool_results':[]}}}
            for index,group in enumerate(groups,1)]


def write_journal(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in rows))


class GateTests(unittest.TestCase):
    def reject(self,data,reason):
        with self.assertRaisesRegex(ValueError,reason):v.validate_summary(*data)

    def test_complete_29_child_structure(self):self.assertEqual(len(v.validate_summary(*fixture())),29)

    def control_log(self):
        return 'test_one (__main__.Demo.test_one) ... ok\ntest_two (__main__.Demo.test_two) ... ok\n\nRan 2 tests in 0.01s\n\nOK\n'

    def test_control_log_exact_named_suite(self):
        v.verify_control_log(self.control_log(),['Demo.test_one','Demo.test_two'])

    def test_control_log_rename_same_count_rejected(self):
        baseline=self.control_log();v.verify_control_log(baseline,['Demo.test_one','Demo.test_two'])
        with self.assertRaisesRegex(ValueError,'named control suite differs'):
            v.verify_control_log(baseline.replace('test_two','test_other'),['Demo.test_one','Demo.test_two'])

    def test_control_log_duplicate_same_count_rejected(self):
        baseline=self.control_log();v.verify_control_log(baseline,['Demo.test_one','Demo.test_two'])
        with self.assertRaisesRegex(ValueError,'named control suite differs'):
            v.verify_control_log(baseline.replace('test_two','test_one'),['Demo.test_one','Demo.test_two'])

    def test_control_log_wrong_summary_rejected(self):
        baseline=self.control_log();v.verify_control_log(baseline,['Demo.test_one','Demo.test_two'])
        with self.assertRaisesRegex(ValueError,'missing exact control success summary'):
            v.verify_control_log(baseline.replace('Ran 2','Ran 3'),['Demo.test_one','Demo.test_two'])

    def test_missing_child_rejected(self):
        data=fixture();data[0]['checks'].pop();self.reject(data,'incomplete or duplicate child coverage')

    def test_duplicate_child_rejected(self):
        data=fixture();data[0]['checks'][-1]=data[0]['checks'][0];self.reject(data,'incomplete or duplicate child coverage')

    def test_stdout_numeric_type_mismatch_rejected(self):
        data=fixture();data[3]['batch-8-r1']['messages']=256.0;self.reject(data,'stdout/result mismatch')

    def test_boolean_returncode_rejected(self):
        data=fixture();data[2]['generate']['returncode']=False;self.reject(data,'child failed')

    def test_changed_source_map_rejected(self):
        data=fixture();data[0]['source_and_binary_hashes_after']={'synthetic':'b'*64};self.reject(data,'source/binary input changed')

    def test_wrong_derived_total_rejected(self):
        data=fixture();data[0]['workloads'][0]['requested_bytes_sum']+=1;self.reject(data,'derived workload total mismatch')

    def test_rollback_unrelated_reason_rejected(self):
        data=fixture();change(data,'rollback-incoming','error','permission denied');self.reject(data,'unrelated rollback rejection')

    def test_expected_corpus_fixed_ids_and_text(self):
        corpus=v.expected_corpus();self.assertEqual(len(corpus),256)
        self.assertEqual(corpus[0]['id'],'11111111-1111-4111-8111-000000000000')
        self.assertEqual(corpus[-1]['parts'][0]['part_id'],'22222222-2222-4222-8222-0000000000ff')
        self.assertTrue(all(len(message['parts'][0]['payload']['Text']['text'])==256 for message in corpus))

    def test_independent_journal_mutations_have_specific_failures(self):
        groups=[v.expected_corpus()[:2],v.expected_corpus()[2:4]]
        with tempfile.TemporaryDirectory(prefix='group-journal-gate-') as temporary:
            path=Path(temporary)/'journal.jsonl';baseline=records(groups)
            write_journal(path,baseline);v.check_journal(path,groups)
            cases=[]
            changed=copy.deepcopy(baseline);changed[1]['payload']['value']['messages'][0]['parts'][0]['part_id']='changed';cases.append((changed,'exact stored message group mismatch'))
            changed=copy.deepcopy(baseline);changed[1]['session_seq']=2.0;cases.append((changed,'wrong journal schema/sequence'))
            changed=copy.deepcopy(baseline);changed[1]['record_id']=changed[0]['record_id'];cases.append((changed,'duplicate/missing record id'))
            changed=copy.deepcopy(baseline);changed[1]['payload']['storage']='blob';cases.append((changed,'independent journal blob confound'))
            for changed,reason in cases:
                write_journal(path,baseline);v.check_journal(path,groups)
                write_journal(path,changed)
                with self.assertRaisesRegex(ValueError,reason):v.check_journal(path,groups)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate JSON key'):json.loads('{"x":1,"x":2}',object_pairs_hook=v.pairs)

    def test_complete_filesystem_gate_then_causal_mutations(self):
        # All files below are authored synthetic JSON/plain-text, never executed.
        with tempfile.TemporaryDirectory(prefix='append-group-gate-') as temporary:
            root=Path(temporary);package=root/'package';(package/'src').mkdir(parents=True)
            binary=root/'not-an-executable';binary.write_text('synthetic bytes')
            entries=[]
            for name in ['Cargo.toml','Cargo.lock','run_group_probe.py','src/allocation.rs','src/main.rs']:
                path=package/name;path.write_text('synthetic '+name);entries.append({'path':name,'bytes':path.stat().st_size,'sha256':v.digest(path)})
            receipt=package/'SOURCE-RECEIPT.json';receipt.write_text(json.dumps({'core_pin':v.PIN,'files':entries}));receipt_hash=v.digest(receipt)
            output=root/'evidence';output.mkdir();corpus=v.expected_corpus();corpus_path=output/'corpus.json';corpus_path.write_text(json.dumps(corpus,separators=(',',':')))
            data=fixture();data[0]['corpus_sha256']=v.digest(corpus_path);change(data,'generate','corpus_bytes',corpus_path.stat().st_size)
            hashes={str(path):v.digest(path) for path in [binary,package/'Cargo.toml',package/'Cargo.lock',package/'run_group_probe.py',package/'src/allocation.rs',package/'src/main.rs']}
            data[1].update(core_pin=v.PIN,source_and_binary_hashes_before=hashes,limits={'child_wall_seconds':60,'child_cpu_seconds':30,'child_address_space_bytes':512*1024**2,'max_child_file_bytes':8*1024**2,'disk_reserve_bytes':1024**3})
            data[0]['source_and_binary_hashes_after']=hashes
            data[1]['isolated_child_environment']={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',**{key:str(output/leaf) for key,leaf in [('HOME','home'),('XDG_CONFIG_HOME','xdg-config'),('XDG_CACHE_HOME','xdg-cache'),('XDG_DATA_HOME','xdg-data'),('TMPDIR','tmp')]}}
            for name,(command,count,batch) in v.checks().items():
                if command=='generate':args=['generate',str(corpus_path)]
                elif command=='rollback':
                    dataset=output/('dataset-'+name);session=dataset/'session';args=['rollback',str(dataset),str(corpus_path),count]
                    change(data,name,'session_dir',str(session))
                    for filename in ['before-rejection.journal.jsonl','after-rejection.journal.jsonl']:write_journal(dataset/filename,records([corpus[:1]]))
                    write_journal(session/'journal.jsonl',records([corpus[:1],corpus[1:3]]))
                else:
                    base=name.removesuffix('-reopen');dataset=output/('dataset-'+base);session=dataset/'session'
                    args=[command,str(dataset if command=='run' else session),str(corpus_path),str(count),str(batch)]
                    if command=='run':
                        write_journal(session/'journal.jsonl',records([corpus[index:index+batch] for index in range(0,count,batch)]))
                        history=dataset/'final-history.json';history.write_text(json.dumps(corpus[:count],separators=(',',':')))
                        change(data,name,'session_dir',str(session));change(data,name,'final_history_file',str(history))
                        if count==256:
                            row=next(row for row in data[0]['workloads'] if row['name']==name);row.update(final_history_sha256=v.digest(history),journal_sha256=v.digest(session/'journal.jsonl'))
                data[2][name]['command']=[str(binary),*args]
                (output/(name+'.stdout.json')).write_text(json.dumps(data[3][name]));(output/(name+'.process.json')).write_text(json.dumps(data[2][name]))
            result_path=output/'result.json';result_path.write_text(json.dumps(data[0]));(output/'environment.json').write_text(json.dumps(data[1]))
            self.assertEqual(v.verify(output,package,binary,receipt_hash)['required_children'],29)
            after=output/'dataset-rollback-active/after-rejection.journal.jsonl';original=after.read_bytes();after.write_bytes(original+b' ')
            with self.assertRaisesRegex(ValueError,'rollback evidence bytes changed'):v.verify(output,package,binary,receipt_hash)
            after.write_bytes(original);self.assertEqual(v.verify(output,package,binary,receipt_hash)['status'],'verified')
            changed=copy.deepcopy(corpus);changed[0]['id']='wrong-id';corpus_path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,'deterministic corpus content/IDs mismatch'):v.verify(output,package,binary,receipt_hash)


if __name__=='__main__':unittest.main()
