"""Run the shipped pure Mermaid engine on an authored diagram, not its worker, host, chat or a real profile."""
from pathlib import Path
import argparse,hashlib,json,subprocess as sp,tempfile,time,xml.etree.ElementTree as ET,shutil,os
p=argparse.ArgumentParser(description=__doc__);p.add_argument('extensions',type=Path);p.add_argument('--node',default='node');p.add_argument('--out',type=Path);a=p.parse_args();root=Path(__file__).resolve().parent
pin='ef064381d2194d95faef2b85f6cc3a1c34c6b975';name='packages/mermaid-render/vendor/pele/pele.mjs';blob=sp.check_output(['git','-C',a.extensions,'show',pin+':'+name])
assert hashlib.sha256(blob).hexdigest()=='a87cc1dc5b2334ccfe32fd0aa5c66f2bb1006b035642976031f589d70c6bf9c7'
node=shutil.which(a.node);assert node
with tempfile.TemporaryDirectory() as td:
 t=Path(td);e=t/'engine.mjs';e.write_bytes(blob);q=(root/'diagram.mmd').read_text()
 code="import {render} from './engine.mjs';const r=await render("+json.dumps(q)+");console.log(JSON.stringify(r));"
 start=time.perf_counter()
 res=sp.run([node,'--permission','--allow-fs-read='+str(e),'--input-type=module','-e',code],cwd=t,env={'PATH':os.path.dirname(node),'HOME':td,'TZ':'UTC'},capture_output=True,text=True,timeout=15)
 if res.returncode:print(res.stderr[-1500:]);raise SystemExit(res.returncode)
 raw=json.loads(res.stdout);svg=raw['svg'];doc=ET.fromstring(svg);assert doc.tag.endswith('}svg');texts=' '.join(doc.itertext());assert all(x in texts for x in ['Choose','Preview','Compare'])
 assert not any(x.tag.rsplit('}',1)[-1]=='script' for x in doc.iter());assert not any('href' in k and v.startswith(('http','//')) for x in doc.iter() for k,v in x.attrib.items())
 if a.out:a.out.write_text(svg+'\n')
 print('Pele 1.12.0, Node '+sp.check_output([node,'--version'],text=True).strip()+': real bundled render produced a parsed SVG with labels Choose / Preview / Compare. Pure engine only, no worker, plugin, GUI or model. Output UTF-8 bytes:',len(svg.encode()),'elapsed (s):',round(time.perf_counter()-start,3))
