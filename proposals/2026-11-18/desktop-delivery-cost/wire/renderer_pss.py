"""Separate renderer PSS only, never app-tree or GUI PSS. Two complete Extension checkouts with --dev builds."""
from pathlib import Path
import hashlib, importlib.util, json, os, statistics, sys, threading, time
from contextlib import closing

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
prose = 'Обычный вопрос про файл: x < y && y > z. \n**это буквальный текст**\n'
def payload(url,rev):
    return prose*512 + (' https://example.org/x' if url else '') + ' ' + str(rev % 2)
def sample(proc):
    return int(next(l for l in Path(f'/proc/{proc.pid}/smaps_rollup').read_text().splitlines() if l.startswith('Pss:')).split()[1])
def render(p,source,rev):
    view='content:synthetic-user-body'
    p.send({'type':'render','surface':'content','view':view,'session_dir':'/fixture-session','argument':'synthetic-user-body',
        'content':{'language':'text/plain','source':source,'source_revision':rev,'context':{'languages':[],'contributors':{}}}})
    msg=p.wait(lambda m:m.get('view')==view and m.get('source_revision')==rev)
    assert msg['type']=='view' and msg['root']['type']=='rich_text'
    return msg
def run(mod,package,url):
    with closing(mod.Process(package, '', preview=True)) as p:
        # Confirm the OS actually launched the claimed executable, not an intermediate shell.
        exe=Path(f'/proc/{p.process.pid}/exe').resolve(); assert exe.samefile(package/'bin'/'markdown-render')
        render(p,'warm up',0)
        idle=sample(p.process); samples=[]; done=threading.Event()
        def watch():
            while not done.is_set():
                samples.append(sample(p.process));done.wait(.001)
        t=threading.Thread(target=watch); t.start()
        digest=hashlib.sha256()
        try:
            for rev in range(1,9):
                msg=render(p,payload(url,rev),rev)
                assert ('<a href=' in msg['root']['html'])==url
                digest.update(json.dumps(msg,sort_keys=True,ensure_ascii=False).encode())
                samples.append(sample(p.process))
        finally:
            done.set();t.join()
        settled=sample(p.process)
        return {'after_warmup_pss_kib':idle,'sampled_max_pss_kib':max(samples),'after_8_responses_pss_kib':settled,
                'samples_including_reply_boundaries':len(samples),'response_digest':digest.hexdigest()}
def main():
    roots=[Path(p).resolve() for p in sys.argv[1:]]
    assert len(roots)==2 and sha(roots[0]/'tests/wire.py')==sha(roots[1]/'tests/wire.py')
    spec=importlib.util.spec_from_file_location('stock_wire',roots[0]/'tests/wire.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    packages=[p/'packages/markdown-render' for p in roots]
    hashes=[sha(p/'bin/markdown-render') for p in packages]
    assert hashes[0]!=hashes[1]
    rows={}
    for url in [False,True]:
        pairs=[]
        for i in range(8):
            sides=[None,None]
            for j in ([0,1] if i%2==0 else [1,0]): sides[j]=run(fixture,packages[j],url)
            assert sides[0]['response_digest']==sides[1]['response_digest']
            pairs.append(sides)
        medians=[{key:statistics.median([pair[j][key] for pair in pairs]) for key in ['after_warmup_pss_kib','sampled_max_pss_kib','after_8_responses_pss_kib']} for j in [0,1]]
        rows['with_url' if url else 'no_url']={'bytes':len(payload(url,1).encode()),'medians_before_after':medians,'pairs_before_after':pairs}
    print(json.dumps({'binary_sha256_before_after':hashes,'unit':'KiB Linux Pss in /proc/<actual-child-pid>/smaps_rollup; sampled maximum, not kernel high-water-mark','rows':rows},indent=2))
if __name__=='__main__':main()
