from pathlib import Path
import subprocess,json,sys
outdir=Path('evidence'); pad=['',' ','  ','\u00a0','\u202f','\u3000','\t']
seeds=['','°C','Итого:', 'кВт·ч','12\u202f345','français','温度','مرحبا','cafe\u0301',
       'null','true','false','123','42','-0.25','"строка"','[]','{}','[1,2]','80%']
raws=list(dict.fromkeys(l+s+r for l in pad for s in seeds for r in pad))
typed=[0,42,-5,0.25,True,False,[],{},['см'],{'unit':'кг'}]   # deliberate JSON null is an unset control
inputs=raws+typed+[None]
payload=''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in inputs).encode()
def run(label,path):
    r=subprocess.run([path],input=payload,capture_output=True,check=True);rows=[json.loads(s) for s in r.stdout.decode().splitlines()]
    assert len(rows)==len(inputs)
    failures=0
    for i,(v,rec) in enumerate(zip(inputs,rows)):
        assert rec['original']==v
        if v is None:
            assert rec['absent']; continue
        if rec['absent'] or type(rec['parsed'])!=type(v) or rec['parsed']!=v:failures+=1
    print(label, 'value cases',len(inputs)-1,'failed',failures,'clearing null correct')
    return failures,rows
f0,old=run('before',sys.argv[1]);f1,new=run('after',sys.argv[2])
for v,o,n in zip(inputs,old,new):
    assert o['manual']==n['manual'] # no changes to typing new raw values of any kind
    if isinstance(v,str):
        if not v or v.strip()!=v:
            assert json.loads(n['shown'])==v
        elif v in ['true','null','123','"строка"','[]','{}']:
            assert o['shown']==n['shown'] and json.loads(n['shown'])==v
    else:
        assert o==n
assert f0>0 and f1==0
lookup={v:r for v,r in zip(raws,new[:len(raws)])}
for v,w in [('',None),(' ',None),('null',None),('true',True),('123',123),('[]',[]),('{}',{}),('"строка"','строка'),('80%','80%')]:
    assert lookup[v]['manual']==w
print('All direct-entry projections unchanged, including typed null/clearing, booleans, numbers, arrays/objects and non-JSON text.')
bad_examples=['','Итого: ','\u202f°C','\u202f42\u202f','\u202fnull\u202f',' 123 ','true','12\u202f345']
witness=[]
for v in bad_examples:
    i=raws.index(v);witness.append([v,old[i],new[i]])
(outdir/'witness.json').write_text(json.dumps(witness,ensure_ascii=True,indent=2)+'\n')
