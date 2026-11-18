"""Compare the pinned neutral quota DTO and display-only extension functions.
Arguments: CORE EXTENSIONS_BEFORE EXTENSIONS_AFTER RUSTC SERDE_DEPS_DIR.
No service/clock access, provider, project runners or real account."""
from pathlib import Path
import tempfile,subprocess as sp,sys,itertools as it,json
c,b,a,r,lib=map(Path,sys.argv[1:6]); here=Path(__file__).resolve().parent
def clean(s):return '\n'.join(l for l in s.splitlines() if not l.startswith('//!'))
core=clean((c/'crates/proteus-contracts/src/contracts/model_quota.rs').read_text().split('impl ModelQuotaSnapshot {')[0])
def program(t,name,src):
 files=[]
 for n in ('describe','view'):
  text=clean((src/'packages/quota/src'/f'{n}.rs').read_text().split('#[cfg(test)]')[0]);files.append(text)
 stub=(here/'main.rs.in').read_text().replace('/*DTO*/',core).replace('/*DESC*/',files[0]).replace('/*VIEW*/',files[1])
 f=t/(name+'.rs');f.write_text(stub);exe=t/name
 cmd=[r,'--edition=2024','-Awarnings',f,'-L','dependency='+str(lib),'-o',exe]
 for l in ('serde','serde_json'):cmd+=['--extern',l+'='+str(next(lib.glob('lib'+l+'-*.rlib')))]
 sp.run(cmd,check=True);return exe
def readings(path,snaps):return [json.loads(l) for l in sp.run([path],input=''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in snaps),text=True,stdout=sp.PIPE,check=True).stdout.splitlines()]
marker='применим';unknown='неизвестн'
def says_unknown(s):return marker in s.casefold() and unknown in s.casefold()
def noteq(b,a):return b!=a
def snap(name,availability,limited,usages,info,reverse):
 def make(winid,v):return {'id':winid,'used_percent':v,'duration_seconds':None,'resets_at':None,'amount':{'used':12.35,'limit':42.75,'unit':'ед.'}}
 bucket={'id':'X-17','name':name,'allowed':availability,'limit_reached':limited,'windows':[make(f'W{i}',n) for i,n in enumerate(usages)]}
 if info!='missing':bucket['informational']=info
 other={'id':'Y-18','name':'Сосед','allowed':True,'limit_reached':False,'windows':[make('N',25.)]}
 return {'observed_at':101,'plan':'Пример','credits':{'available':True,'unlimited':False,'balance':'3.30'},'notices':['Замечание'],'buckets':([other,bucket] if reverse else [bucket,other])}
def verify_bundles():
 snaps=[];cases=[]
 for n,al,lim,us,rev in it.product((None,'','Бюджет Z'),(None,True,False),(None,True,False), ((),(0.,),(100.,),(112.,6.25)),(False,True)):
  for flag in ('missing',False,True):
   snaps.append(snap(n,al,lim,us,flag,rev));cases.append((n,al,lim,us,flag,rev))
 with tempfile.TemporaryDirectory() as td:
  t=Path(td)
  pre,post=program(t,'pre',b),program(t,'post',a)
  bef,aft=readings(pre,snaps),readings(post,snaps)
  allinfo=[]
  for n in (0,1,2,3):
   for silent in (False,True):
    sample=snap('Два одинаковых заголовка', None,None,(() if silent else (12.5,)),True,False)
    first=sample['buckets'][0];sample['buckets']=[dict(first,id=f'entry-{i}') for i in range(n)];allinfo.append(sample)
  for sample,(x,xs,xc),(y,ys,yc) in zip(allinfo,readings(pre,allinfo),readings(post,allinfo)):
   count=len(sample['buckets']);assert x is None and y is None
   q='Справочный лимит: неизвестно, действует ли он для текущей модели.'
   assert [v for v in ys if q not in v]==xs and sum(q in v for v in ys)==count
   assert [z for z in yc if z.get('type')!='card']==[z for z in xc if z.get('type')!='card']
   assert len(yc)==len(xc)
   assert sum(c.get('type')=='card' and q in c['title'] for c in yc)==count
   for old,new in zip(xc,yc):
    assert {k:v for k,v in old.items() if k!='title'}=={k:v for k,v in new.items() if k!='title'}
  q='Справочный лимит: неизвестно, действует ли он для текущей модели.'
  big={'observed_at':101,'plan':None,'credits':None,'notices':[], 'buckets':[{'id':str(i),'name':None,'allowed':False,'limit_reached':None,'windows':[],'informational':True} for i in range(2499)]}
  (x,xs,xc),=readings(pre,[big]);(y,ys,yc),=readings(post,[big])
  def nodes(obj):return 1+sum(nodes(x) for x in obj.get('children',[]))
  assert x==y==None and len(xc)==len(yc)==2500 and sum(map(nodes,xc))==sum(map(nodes,yc))==4999
  assert nodes({'type':'stack','children':xc})==nodes({'type':'stack','children':yc})==5000
  for i,(old,new) in enumerate(zip(xc,yc)):
   if i<len(big['buckets']):assert new==dict(old,title=old['title']+' · '+q)
   else:assert new==old
  assert [v for v in ys if q not in v]==xs and sum(q in v for v in ys)==2499
  print('Large synthetic fixture: 2499 informational groups with one reported status each, plus timestamp = 4999 returned widget nodes; with one local root = exactly 5000 both before and after. 2499 titles qualified, no other node differences. No host mount.')
  print('Eight additional snapshots: 0..3 informational groups with identical display names and distinct IDs, with or without windows. All remain numeric None; one qualified title per group, including zero qualifications on empty inventory.')
 info=0;silent=0;row_details=0;nochange=0;amounts=0
 scope='Справочный лимит: неизвестно, действует ли он для текущей модели.'
 for i,((n,al,lim,us,flag,rev),(x,xs,xc),(y,ys,yc)) in enumerate(zip(cases,bef,aft)):
  expected=min([75.]+([max(0,100-v) for v in us] if flag!=True else []))
  assert x==y==expected
  idx=1+int(rev)
  if flag!=True:
   assert (xs,xc)==(ys,yc);nochange+=1
   if flag=='missing':assert bef[i]==bef[i+1] and aft[i]==aft[i+1]
  else:
   info+=1
   assert xc[:idx]==yc[:idx] and xc[idx+1:]==yc[idx+1:]
   old,new=xc[idx],yc[idx]
   assert new==dict(old,title=old['title']+' · '+scope)
   # Plan appears first; if the other bucket was first its window contributes one line.
   p=1+int(rev);assert ys==xs[:p]+[(n or 'X-17')+': '+scope]+xs[p:]
   silent+=len(us)==0 and lim is not True and al is not False
   row_details+=len(old['children']);amounts+=len(us)
 print(f'{len(snaps)} neutral typed DTO roundtrips. {info} informational: exactly one explanatory line before its tooltip group and one suffix on its existing matching popup card title; {silent} previously tooltip-silent included. {nochange} omitted/false cases byte-identical. {row_details} original card children and {amounts} amount-bearing windows preserved at the reference group; all limiting remainders, neighbors, names, notices/credits, timestamps and ability indicators unchanged.')
verify_bundles()
