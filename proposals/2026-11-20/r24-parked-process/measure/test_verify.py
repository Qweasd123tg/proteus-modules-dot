"""Reducer controls with sparse invented PID records. Does not spawn or signal a peer."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from verify import check_resource_samples, checked_journal, clock_bounds, snapshot_prefixes


def frames(cold):
    phases = [('round_start',100,0),('peer_model_entered',110,0),('all_models_entered',110.1,0),
              ('round_settled',200,0),('interround_idle',700,None),
              ('round_start',2500,1),('peer_model_entered',2510,1),('all_models_entered',2510.1,1),
              ('round_settled',2600,1),('resident_idle',3100,None),('teardown',4920,None)]
    events=[dict(phase=k,elapsed_ms=t,data={} if r is None else dict(round=r)) for k,t,r in phases]
    def sample(phase,stamp,pid):
        def row(pid,ppid,name):
            return dict(pid=pid,parent=ppid,name=name,start_ticks=2*pid,Pss=4,SwapPss=0)
        rows=[row(1,0,'parent')]+[row(2+i,1,'worker') for i in range(5)]
        if pid:
            rows += [row(pid,1,'proteus')]+[row(pid+1+i,pid,'module') for i in range(5)]
        return dict(phase=phase,sample_begin_ms=stamp,sample_end_ms=stamp+1,processes=rows,pss_swap_kib=4*len(rows))
    second = 20 if cold else 10
    return events, [sample('all_models_entered',120,10)] + [
        sample('interround_idle',1000,None if cold else 10) for _ in range(4)] + [
        sample('all_models_entered',2520,second)] + [
        sample('resident_idle',3500,None if cold else 10) for _ in range(4)]


class Proof(unittest.TestCase):
    def test_cold_replaced_warm_retained(self):
        for cold in (True,False):
            ev,ss=frames(cold)
            data=check_resource_samples(ev,ss,1,0 if cold else 1,(1,2),'proteus',[-5,8])
            self.assertEqual(data['rounds'][1]['from_round_start_to_first_tool_ms'],10)
    def test_cold_rejects_retained_or_unobserved_peer(self):
        e,s=frames(True)
        for i in (1,5):
            malformed=copy.deepcopy(s)
            malformed[i]['processes']=s[0]['processes']
            with self.assertRaises(ValueError):
                check_resource_samples(e,malformed,1,0,(1,2),'proteus',[-5,8])
        with self.assertRaises(ValueError):
            check_resource_samples(e,[x for x in s if x['phase']!='interround_idle'],1,0,(1,2),'proteus',[-5,8])
    def test_delayed_event_labels_do_not_admit_boundary_samples(self):
        ev,ss=frames(True)
        torn=copy.deepcopy(ss[1])
        torn.update(phase='resident_idle',sample_begin_ms=4900,sample_end_ms=4901,processes=torn['processes'][:1])
        # Driver's teardown marker came later, but the nominal window and fixed
        # margin close before this stale-labelled sample. Central contamination
        # with the same PIDs must still fail, irrespective of phase labels.
        clock=clock_bounds(dict(phase='parent_start',elapsed_ms=.1),3.1)
        data=check_resource_samples(ev,ss+[torn],1,0,(1,2),'proteus',clock)
        self.assertEqual(data['idle']['resident_idle']['stable_samples'],4)
        torn.update(phase='teardown',sample_begin_ms=4000,sample_end_ms=4001)
        with self.assertRaises(ValueError):
            check_resource_samples(ev,ss+[torn],1,0,(1,2),'proteus',clock)

    def test_prefix_rejects_rewrite_duplicate_turn_and_missing_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp); d=w/'config/sessions/test'; d.mkdir(parents=True)
            p=d/'journal.jsonl'
            def segment(turn,base):
                result=[]
                for i,(kind,value) in enumerate([
                      ('turn_opened',dict(base_history_revision=base)),
                      ('model_request_recorded',{'request':{'messages':[{'role':'Tool','tool_call_id':'old-call'}]}}),
                      ('tool_effect_recorded',{'result':{'call_id':turn+'-call'}}),
                      ('turn_settled',dict(status='success',output={'metadata':{'executed_tools':['read_file']}}))]):
                    result.append(json.dumps(dict(kind=kind,turn_id=turn,session_id='s',thread_id=turn+'physical',
                                                  record_id=f'{turn}:{i}',payload={'value':value}))+'\n')
                return ''.join(result)
            a,b=segment('old',0),segment('new',1)
            p.write_text(a)
            snap=snapshot_prefixes(w,1)
            meta=dict(session_dir=str(d),session_id='s')
            p.write_text(a+b)
            self.assertEqual(checked_journal(w,meta,snap)[1],['old','new'])
            for broken in (a.replace('"old"','"bad"')+b,a+a,a+segment('new',0),a+b.replace('old-call','absent'),a+b+b):
                p.write_text(broken)
                with self.assertRaises(ValueError):
                    checked_journal(w,meta,snap)


if __name__=='__main__': unittest.main()
