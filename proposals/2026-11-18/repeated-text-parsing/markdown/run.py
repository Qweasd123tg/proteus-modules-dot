"""Actual extension JSONL. Compare whole answers/revisions; timing ELFs never log parser counters."""
import collections,hashlib,json,random,statistics,subprocess,sys,time
from pathlib import Path
from fixtures import make
F=make()
def cuts(s,n):
 b=s.encode(); return [b[:len(b)*i//n].decode(errors='ignore') for i in range(1,n+1)]
def series():
 prose=F['prose'];ref=F['late-ref']
 special=('# Результат\r\n\r\n- [x] **GFM** и ~~так~~\r\n- [ ] $x^2$\r\n\r\n'
          '| A | B |\n| - | - |\n| inline `code` | [$y$](https://example.org) |\n\n'
          '> <span>literal</span>\n\n' + ('Проза, **вариант** и `метка`.\n\n'*22))
 fenced='\n\n'.join([special,'```mermaid\nA-->B\n```',special,'$$\r\nx^2\r\n$$',special])
 open_code=special+'\r\n~~~rust\r\nfn f(){\r\n'+('    code();\n'*64)
 cases={**{f'prose-prefix-{n}':cuts(prose,n) for n in [1,4,16,64]},
        'prose-static-repeat':[prose]*5,'late-definition':cuts(ref,16),
        'gfm-inline-math-html':cuts(special,16), 'closed-fence-display-math':cuts(fenced,16),
        'multi-static-repeat':[fenced]*5,'unclosed-code':cuts(open_code,16),
        'unclosed-math':cuts(special+'\n\n$$\nα^2\n',16)}
 return cases
def fields(source,rev,view='content:assistant-block',langs=('mermaid','latex','tex','json-render')):
 return {'type':'render','surface':'content','view':view,'context':'fixture','argument':'assistant-block','session_dir':'/synthetic',
    'content':{'language':'text/markdown','source':source,'source_revision':rev,'context':{'languages':list(langs)}}}
def enc(x):return json.dumps(x,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
hello=enc({'type':'hello','protocol':4,'features':['surfaces.content.v1','widgets.rich_text.v1','widgets.rich_text.inlines.v1','widgets.content.v1','widgets.code_embedded.v1'],'workspace':'/synthetic','server':{'origin':'','token':''}})
def requests(srcs):return [enc(fields(s,i)) for i,s in enumerate(srcs,1)]
def validate(line,rev):
 m=json.loads(line)
 assert m['type']=='view' and m['source_revision']==rev and m['root']['type']=='stack',(list(m),rev)
 return m['root']
def packet(binary,reqs,count):
 r=subprocess.run([binary],input=hello+b''.join(reqs),capture_output=True,timeout=120,check=True)
 outputs=r.stdout.splitlines(keepends=True);assert len(outputs)==len(reqs)
 for i,l in enumerate(outputs,1):validate(l,i)
 digest=hashlib.sha256(r.stdout).hexdigest()
 if not count:assert not r.stderr;return digest,{}
 rows={}
 for l in r.stderr.decode().splitlines():
  tag,k,n=l.split();n=int(n)
  if tag=='MDFRAME':
   key=int(k);assert key not in rows;rows[key]={'source_bytes':n,'stages':[]}
  else:
   assert tag=='MDPASS' and k in ['route','inline','guard','html'];rows[key]['stages'].append([k,n])
 assert len(rows)==len(reqs)
 return digest,rows
def summarize(rows):
 total=collections.defaultdict(lambda:[0,0])
 for f in rows.values():
  for k,n in f['stages']:total[k][0]+=1;total[k][1]+=n
 return dict(total)
def time_series(binary,reqs):
 # Prebuilt requests, same warmed process, separate untimed view so retained state starts empty on the target view.
 p=subprocess.Popen([binary],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 try:
  p.stdin.write(hello+enc(fields('warm',0,'content:warm')));p.stdin.flush();validate(p.stdout.readline(),0)
  raw=[];samples=[]
  for req in reqs:
   t=time.perf_counter_ns();p.stdin.write(req);p.stdin.flush();line=p.stdout.readline();end=time.perf_counter_ns()
   samples.append((end-t)*1e-6);raw.append(line)
  p.stdin.close();assert p.wait(timeout=10)==0 and not p.stderr.read()
  for i,l in enumerate(raw,1):validate(l,i)
  return {'total_ms':sum(samples),'last_ms':samples[-1],'digest':hashlib.sha256(b''.join(raw)).hexdigest()}
 finally:
  if p.poll() is None:p.kill();p.wait()
def corpus():
 stems=['','\r','\r\n','\n','\t',' ','  ','   ','    ','  \t','\u00a0','\u2003','\ufeff','я🙂']
 bits=['```','``','~~~','~~','$$','$','[a]: /one','[a\n  z]: /two','[a] : <fake>','[a\\]]: /three','![a][ref]','[p][a]',
       'line \t code','> [x]: /nested','> > $$$\r\n> x\r\n> $$$','- [x]\n  code','    A\r\n    B','# H\n\n---','<div>x & y</div>','&#91;a&#93;&#58; /fake',
       '```md\r\n~~~\r\n```\r','~~~json\nx\n~~~','~~a~~','a $x$ and $100', '```x\ny','| A | B |\n| - | - |','[a]: /b\n\n[a]']
 rng=random.Random(4019)
 sources=[a+b+'\n\nend' for a in stems for b in bits]+[rng.choice(stems)+''.join(rng.choices(bits,k=rng.randrange(2,7))) for _ in range(300)]
 return [enc(fields(s,i,'content:d'+str(i%4),('latex',) if i%3 else ())) for i,s in enumerate(sources,1)]
def main():
 mode,rawpaths=sys.argv[1],sys.argv[2:];bins=list(map(lambda p:str(Path(p).resolve()),rawpaths))
 assert len(bins)==2;res={'binary_sha256':[hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in bins],'results':{}}
 assert len(set(res['binary_sha256']))==2
 traces={}
 if mode=='parity':
  reqs=corpus();a,b=[packet(bin,reqs,False)[0] for bin in bins];assert a==b
  res['generated_corpus']={'frames':len(reqs),'full_output_sha256':a}
 for k,srcs in series().items():
  reqs=requests(srcs)
  row={'frames':len(reqs),'final_bytes':len(srcs[-1].encode()),'submitted_utf8_bytes':sum(len(s.encode()) for s in srcs)}
  if mode=='counts':
   (a,x),(b,y)=[packet(bin,reqs,True) for bin in bins];assert a==b
   row.update({'full_output_sha256':a,'before':summarize(x),'after':summarize(y),'per_frame_before':x,'per_frame_after':y})
  elif mode=='time':
   samples=[[],[]];digests=set()
   for i in range(6):
    for side in ([0,1] if i%2==0 else [1,0]):
     v=time_series(bins[side],reqs);digests.add(v.pop('digest'));samples[side].append(v)
   assert len(digests)==1
   row.update({'full_output_sha256':digests.pop(),'ms_before_after_median':[statistics.median(v['total_ms'] for v in s) for s in samples],
               'ms_last_before_after_median':[statistics.median(v['last_ms'] for v in s) for s in samples],'samples_before_after':samples})
  else:
   a,b=[packet(bin,reqs,False)[0] for bin in bins];assert a==b;row['full_output_sha256']=a
  res['results'][k]=row
 print(json.dumps(res,indent=2))
if __name__=='__main__':main()
