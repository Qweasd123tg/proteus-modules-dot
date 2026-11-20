"""Fail closed on resource, identity, durable-prefix, and accepted-work evidence."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

IDLE_GUARD_MS = 200.0
IDLE_WINDOW_MS = 1800
CLOCK_MARGIN_MS = 5.0


def clock_bounds(first_event, received_ms):
    require(first_event['phase']=='parent_start', 'missing initial driver clock marker')
    elapsed = first_event['elapsed_ms']
    # Both clocks are Linux CLOCK_MONOTONIC. Python zero is captured before
    # Popen. By the time the line is received, Rust has already emitted at
    # its elapsed_ms, giving an upper bound on Rust Instant origin.
    latest = received_ms - elapsed
    require(latest >= 0, 'driver/collector clock bracket invalid')
    return [-CLOCK_MARGIN_MS, latest+CLOCK_MARGIN_MS]


def fit_sample(sample, bounds, start_ms, end_ms, guard_ms=0.0):
    lo, hi = bounds
    return (start_ms+hi+guard_ms <= sample['sample_begin_ms'] <=
            sample['sample_end_ms'] <= end_ms+lo-guard_ms)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def field_ids(rows, key):
    return {r[key] for r in rows}


def snapshot_prefixes(work, n):
    paths = sorted((work/'config/sessions').rglob('journal.jsonl'))
    require(len(paths) == n, 'unexpected number of first-turn journals')
    result = {}
    for path in paths:
        blob = path.read_bytes()
        records = [json.loads(line) for line in blob.splitlines()]
        turns = [r['turn_id'] for r in records if r['kind']=='turn_settled']
        require(len(turns)==1 and field_ids(records, 'turn_id')==set(turns),
                'first idle snapshot must have one settled turn')
        result[str(path.relative_to(work))] = dict(bytes=len(blob), sha256=sha(blob), turn=turns[0])
    return result


def checked_journal(work, meta, prefix):
    p = (Path(meta['session_dir'])/'journal.jsonl').resolve()
    key = str(p.relative_to(work))
    require(key in prefix and p.is_relative_to(work/'config/sessions'), 'result references another journal')
    original = prefix[key]
    blob = p.read_bytes()
    require(len(blob) > original['bytes'] and sha(blob[:original['bytes']])==original['sha256'],
            'second turn replaced or rewrote first-turn journal bytes')
    first = [json.loads(line) for line in blob[:original['bytes']].splitlines()]
    added = [json.loads(line) for line in blob[original['bytes']:].splitlines()]
    require(added and added[0]['kind']=='turn_opened', 'journal suffix must start a new turn')
    ids, threads = [], []
    for rows in (first, added):
        counts = Counter(x['kind'] for x in rows)
        require(counts['turn_opened']==counts['turn_settled']==counts['tool_effect_recorded']==1,
                'expected exactly one open, settle, and file effect per turn')
        require(len(field_ids(rows,'turn_id'))==1, 'more than one turn in journal segment')
        require(field_ids(rows,'session_id')=={meta['session_id']}, 'durable session does not match result')
        settled = next(r['payload']['value'] for r in rows if r['kind']=='turn_settled')
        require(settled['status']=='success' and settled['output']['metadata']['executed_tools']==['read_file'],
                'expected one successful read_file in each turn')
        tids = field_ids(rows, 'thread_id')
        require(len(tids)==1 and None not in tids, 'mixed physical threads within one turn')
        threads.append(rows[0]['thread_id'])
        ids.append(rows[0]['turn_id'])
    require(ids[0]==original['turn'] and ids[0]!=ids[1], 'reused or changed turn id')
    second_open = added[0]['payload']['value']
    require(second_open['base_history_revision'] > 0, 'resume opened with no historical revision')
    # A cold-opened CLI has a fresh physical root thread. The stable public task,
    # persisted session+directory and history matter, not physical thread equality.
    old_call = next(r['payload']['value']['result']['call_id'] for r in first if r['kind']=='tool_effect_recorded')
    new_call = next(r['payload']['value']['result']['call_id'] for r in added if r['kind']=='tool_effect_recorded')
    require(old_call and new_call and old_call!=new_call, 'reused synthetic file effect call ID')
    seen = False
    for r in added:
        if r['kind']=='tool_effect_recorded':
            break
        if r['kind']=='model_request_recorded':
            v = r['payload']['value']
            # May be the history-compaction hook's auxiliary model call or the
            # first direct model call. Check a specific prior Tool message rather
            # than generic text present in both rounds.
            seen |= any(m.get('role')=='Tool' and m.get('tool_call_id')==old_call
                        for m in v['request']['messages'])
    require(seen, 'new turn did not consume the actual first-turn tool history')
    require(len(field_ids(first+added,'record_id'))==len(first)+len(added), 'duplicate journal record IDs')
    return key, ids, threads


def check_resource_samples(events, samples, peers, cap, parent, comm, clock):
    require(comm and len(comm.encode()) <= 15, 'use a short unambiguous name for the Core binary')
    def id_set(rows):
        return {(p['pid'],p['start_ticks']) for p in rows}
    def peer_rows(s):
        return [p for p in s['processes'] if p['name']==comm and p['parent']==parent[0]]
    def phase(name, round_no=None):
        matches = [e['elapsed_ms'] for e in events if e['phase']==name and
                   (round_no is None or e['data'].get('round')==round_no)]
        require(len(matches)==1, f'missing/duplicate phase {name} round {round_no}')
        return matches[0]
    rounds = []
    cohorts = []
    for r in (0,1):
        lo, hi = phase('round_start',r), phase('round_settled',r)
        active = [s for s in samples if fit_sample(s,clock,lo,hi)]
        require(active and max(len(peer_rows(s)) for s in active)==peers, 'active peer count not observed')
        cohort = set().union(*(id_set(peer_rows(s)) for s in active))
        require(len(cohort)==peers, 'unexpected peer churn during active round')
        cohorts.append(cohort)
        ready = sorted(e['elapsed_ms']-lo for e in events if e['phase']=='peer_model_entered' and e['data']['round']==r)
        require(len(ready)==peers and phase('all_models_entered',r) <= hi, 'missing readiness/overlap')
        rounds.append(dict(sampled_peak_pss_swap_mib=max(s['pss_swap_kib'] for s in active)/1024,
                           from_round_start_to_first_tool_ms=ready[0],
                           from_round_start_to_last_tool_ms=ready[-1],from_round_start_to_all_settled_ms=hi-lo,
                           core_pid_start_ticks=[list(x) for x in sorted(cohort)]))
    require(cohorts[0].isdisjoint(cohorts[1]) if cap==0 else cohorts[0]==cohorts[1],
            'cold cohort was not replaced, or warm cohort changed')
    windows = {}
    for name, cohort, deadline in zip(('interround_idle','resident_idle'),cohorts,
                                      (phase('round_start',1), phase('teardown'))):
        lo = phase(name)
        # The actual teardown marker follows dropping resources, so it is
        # not safe as a lone boundary. Never use samples after the announced
        # nominal idle duration, even with delayed marker receipt or teardown.
        hi = min(lo+IDLE_WINDOW_MS,deadline)
        window = [s for s in samples if fit_sample(s,clock,lo,hi,IDLE_GUARD_MS)]
        require(len(window)>=3, 'not enough stable idle observations')
        for s in window:
            rows = s['processes']
            require(parent in id_set(rows), 'lost original parent')
            require(all('Pss' in p and 'SwapPss' in p for p in rows), 'incomplete measured process')
            require(id_set(peer_rows(s))==(set() if cap==0 else cohort), 'wrong idle core identities')
            # Synthetic split config: parent + four reference components + storage; same per warm child.
            require(len(rows)==6*(1+cap), 'idle worker family missing, extra or orphaned')
            require(sum(p['parent']==parent[0] for p in rows)==5+cap,'wrong parent process topology')
            for p in peer_rows(s):
                require(sum(q['parent']==p['pid'] for q in rows)==5,'incomplete resident peer family')
        windows[name] = dict(stable_samples=len(window), time_guard_ms=IDLE_GUARD_MS, processes=6*(cap+1),resident_child_cores=cap,
                             median_pss_swap_mib=median(s['pss_swap_kib'] for s in window)/1024)
    return dict(rounds=rounds, idle=windows)


def check_run(work,binary,events,samples,prefixes,peers,cap,replays,root_pid,root_start,clock,prefix_time):
    require(prefixes is not None and len(prefixes)==peers, 'first-turn snapshot missing')
    lo = next(e['elapsed_ms'] for e in events if e['phase']=='interround_idle')
    hi = next(e['elapsed_ms'] for e in events if e['phase']=='round_start' and e['data']['round']==1)
    require(fit_sample(prefix_time,clock,lo,min(lo+IDLE_WINDOW_MS,hi),IDLE_GUARD_MS),
            'first journal snapshot was not wholly inside guarded interround idle')
    require(len(replays)==peers and all(r['replay_matched'] and r['settled_turns']==2 for r in replays),
            'both per-turn read-only replays required')
    require(len({r['sha256'] for r in replays})==peers, 'duplicate replayed journal')
    def select(phase, round_no):
        rows = [x['data'] for x in events if x['phase']==phase and x['data']['round']==round_no]
        require(sorted(r['peer'] for r in rows)==list(range(peers)), 'missing or duplicate '+phase)
        return {r['peer']:r for r in rows}
    results = []
    keys = set()
    work_events = [json.loads(line) for line in (work/'config/.proteus/events.jsonl').open()]
    event_counts = defaultdict(Counter)
    for record in work_events:
        event_counts[record['session_id'],record['turn_id']].update(record['event'].keys())
    submitted, returned, finished = [[select(phase,r) for r in (0,1)] for phase in
                                     ('task_submitted','task_result','peer_finished')]
    for i in range(peers):
        id0 = submitted[0][i]['task_id']
        require(id0 and submitted[0][i]['requested'] is None and submitted[1][i]['requested']==id0 and
                submitted[1][i]['task_id']==returned[0][i]['task_id']==returned[1][i]['task_id']==id0,
                'follow-up request/handles/results do not preserve original task ID')
        m0,m1 = [r[i]['metadata'] for r in finished]
        require(m0.get('resumable') is True and m1.get('resumable') is True, 'task not reported resumable')
        session = m0['subagent_session']
        require(all(session[k]==m1['subagent_session'][k] for k in ('session_id','session_dir')),
                'session ID or journal binding changed')
        key, turns, threads = checked_journal(work,session,prefixes)
        require(cap==0 or threads[0]==threads[1], 'unexpected change of warm physical root')
        require(key not in keys, 'multiple peers bound one journal')
        keys.add(key)
        for turn in turns:
            counter = event_counts[session['session_id'],turn]
            require(counter['TurnStarted']==counter['TurnFinished']==counter['ToolFinished']==1 and
                    counter['ModelRequestPrepared']==counter['ModelResponseReceived']==2,
                    'missing/duplicate live invocation or tool effect in a settled turn')
        results.append(dict(peer=i, task_id=id0, session_id=session['session_id'], turns=turns, physical_root_threads=threads))
    require(len({r['task_id'] for r in results})==len({r['session_id'] for r in results})==peers and
            keys==set(prefixes), 'duplicate or missing bindings')
    resources = check_resource_samples(events,samples,peers,cap,(root_pid,root_start),binary.name,clock)
    for i, round_result in enumerate(resources['rounds']):
        # Require actual direct model overlap separately for initial and resumed work.
        round_ids = {(peer['session_id'],peer['turns'][i]) for peer in results}
        active, peak = set(), 0
        events_in_round = (e for e in work_events if (e['session_id'],e['turn_id']) in round_ids)
        for e in sorted(events_in_round,key=lambda e:e['timestamp_ms']):
            key = e['session_id'], e['turn_id']
            if 'ModelRequestPrepared' in e['event']:
                require(key not in active, 'duplicate start without completion')
                active.add(key)
                peak = max(peak,len(active))
            if 'ModelResponseReceived' in e['event']:
                require(key in active, 'response without a matching request')
                active.remove(key)
        require(not active and peak==peers, 'did not observe N in-flight model requests in each round')
        round_result['max_direct_model_requests_in_flight'] = peak
    return dict(status='passed',peers=results,**resources)
