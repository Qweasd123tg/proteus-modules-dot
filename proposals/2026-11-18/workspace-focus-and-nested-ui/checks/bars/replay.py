"""Run with BEFORE render.rs, AFTER render.rs, Extensions catalog.rs, deps directory and rustc. All inputs synthetic."""
import argparse,hashlib,json,math,struct,pathlib,re,subprocess,tempfile
from decimal import Decimal
p=argparse.ArgumentParser()
for name in ('before','after','catalog','deps'):p.add_argument(name,type=pathlib.Path)
p.add_argument('--rustc',default='rustc'); args=p.parse_args()
C=args.catalog.read_text().splitlines(keepends=True)
def sl(a,b):return ''.join(C[a-1:b])
cat=sl(4,4)+sl(6,6)+sl(10,12)+'fn render_json(source:&str)->Result<Value> {\n'+sl(15,17)+sl(20,22)+'}\n'+sl(36,186)+'_=> bail!("outside ordinary test slice"),\n}\nOk(())\n}\n'
template=pathlib.Path(__file__).with_name("probe.rs.in").read_text()
def block(s,start):
    p=s.index(start);n=0;b=s.index('{',p)
    for j in range(b,len(s)):
        if s[j]=='{':n+=1
        if s[j]=='}':
            n-=1
            if not n:return s[p:j+1]
    raise ValueError(start)
def rlib(n):
    files=sorted(args.deps.glob('lib'+n+'-*.rlib'));assert len(files)==1,files;return files[0]
def compile_model(s,stage,td):
    peak=re.search(r'let peak = bars[^;]+;',s).group()
    frac=re.search(r'let fraction = if peak > 0\..*?};',s,re.S).group()
    label='format!("{}{unit}", number(bar.value))'; assert ".child("+label+")" in s
    out=td/stage
    code=template
    for token,v in [('CATALOG',cat),('NUMBER',block(s,'fn number(')),('PEAK',peak),('FRACTION',frac),('LABEL',label)]:code=code.replace('/*'+token+'*/',v)
    src=out.with_suffix('.rs');src.write_text(code)
    cmd=[args.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(args.deps),'--extern','serde_json='+str(rlib('serde_json')),'--extern','anyhow='+str(rlib('anyhow')),src,'-o',out]
    subprocess.run(cmd,check=True);return out
def chart(values,unit):
    return {'type':'bar_chart','bars':[{'label':f'Ряд {i+1}','value':v} for i,v in enumerate(values)],'unit':unit}
T=.005
values=[0.,-0.,math.nextafter(T,0),T,math.nextafter(T,math.inf),.004,.001,12.5,42,1e15,5e-324,2.2250738585072014e-308,.9999,1.12345]
values += [math.ldexp(n/1024,e) for e in range(-1074,12,7) for n in [1,3,17,511,1019]]
groups=[chart([.001,.004]," ms"),chart([0.,0.],"")]
for n in range(0,len(values),29): groups.append(chart(values[n:n+29],['','%',' µs',' мг'][n%4]))
source=''.join(json.dumps(g,ensure_ascii=False)+'\n' for g in groups)
dec=Decimal.from_float
def f32(x):return struct.unpack('>f',struct.pack('>f',x))[0]
def f64bits(s):return struct.unpack('>d',int(s).to_bytes(8,'big'))[0]
with tempfile.TemporaryDirectory() as a:
    a=pathlib.Path(a);out={}
    sb=args.before.read_text();sa=args.after.read_text()
    test=sa[sa.index('#[cfg(test)]\nmod bar_number_tests'):]
    for k,s in [('before',sb),('after',sa)]:
        o=compile_model(s,k,a);r=subprocess.run([o],input=source,text=True,capture_output=True,check=True)
        out[k]=list(map(json.loads,r.stdout.splitlines()))
        st=a/(k+'_test.rs');st.write_text(block(s,'fn number(')+'\n'+test)
        subprocess.run([args.rustc,'--test','--edition=2024',st,'-o',str(st)[:-3]],check=True)
        reg=subprocess.run([str(st)[:-3]],capture_output=True,text=True)
        assert bool(reg.returncode)==(k=='before'),reg.stdout
        print(k,'one exact upstream-ready native regression', 'RED as expected' if reg.returncode else 'GREEN')
    assert len(out['before'])==len(out['after'])==len(groups)
    seen=failures=changes=0
    for a,b,g in zip(out['before'],out['after'],groups):
        unit=g['unit'];assert a['unit']==b['unit']==unit
        assert len(a['rows'])==len(b['rows'])==len(g['bars'])
        vals=[f64bits(y['value_bits']) for y in b['rows']];peak=max(vals)
        for x,y,q,v in zip(a['rows'],b['rows'],g['bars'],vals):
            assert q['label']==x['label']==y['label'];assert x['value_bits']==y['value_bits']
            assert math.isclose(v,q['value'],abs_tol=5e-324,rel_tol=2e-15)
            assert x['fraction']==y['fraction'];assert math.isclose(x['fraction'],f32(v/peak if peak else 0.),abs_tol=1e-45,rel_tol=1.99e-7)
            assert x['text'].endswith(unit) and y['text'].endswith(unit)
            old=Decimal(x['text'].removesuffix(unit));now=Decimal(y['text'].removesuffix(unit))
            seen+=1
            if x['text']!=y['text']:
                changes+=1;assert v>0 and old==0 and now>0
                assert abs(now-dec(v))/dec(v)<=Decimal('0.005')
            if v>0 and old==0:failures+=1
            assert v==0 or now>0
    print('example labels, old:',[r['text'] for r in out['before'][0]['rows']])
    print('example labels, new:',[r['text'] for r in out['after'][0]['rows']],'unchanged fractions:',[r['fraction'] for r in out['after'][0]['rows']])
    print(f'{len(groups)} charts, {seen} bars, {failures} false zero labels → 0; {changes} labels changed, no other label, fraction, unit or category changed in tested fixtures')
