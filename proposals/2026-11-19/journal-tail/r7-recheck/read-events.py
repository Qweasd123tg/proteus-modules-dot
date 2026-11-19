from pathlib import Path
import json
def snapshot(journal, offset):
    with journal.open('rb') as j:
        j.seek(offset)
        recs=list(map(json.loads,j))
    summary=[dict(seq=r['session_seq'],timestamp_ms=r['timestamp_ms'],kind=r['kind']) for r in recs]
    times={r['kind']:r['timestamp_ms'] for r in summary}
    assert len(recs)==6 and summary[-1]['seq']==507,summary
    req=next(r['payload']['value'] for r in recs if r['kind']=='model_request_recorded')
    resp=next(r['payload']['value'] for r in recs if r['kind']=='model_response_recorded')
    assert req['exchange_id']==resp['exchange_id'] and resp['outcome']['status']=='response'
    assert len(req['request']['messages'])==101
    return dict(events=summary,request_to_response_journal_ms=times['model_response_recorded']-times['model_request_recorded'],turn_open_to_settled_journal_ms=times['turn_settled']-times['turn_opened'],source="Extra B candidate-worker run; matching exchange, non-streaming fake model. Integer-ms timestamps of journal request/response records; includes bookkeeping/RPC, not isolated inference latency.")
