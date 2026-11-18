"""Offline newcomer search and generic Markdown-formatting check.
Usage: python probe.py DESKTOP_GIT_DIR EXTENSIONS_GIT_DIR RUSTC LIBMARKDOWN DEPENDENCY_DIR
No Desktop, install, renderer binary, Node, model or external I/O is launched.
"""
from pathlib import Path
import datetime as dt,json,re,subprocess,sys,tempfile,time
d,e,rustc,md,dep=map(Path,sys.argv[1:]); stages={}
def measure(label,action):
 t=time.perf_counter_ns();v=action();stages[label]=round((time.perf_counter_ns()-t)/1e6,2);return v
def blob(repo,pin,src):
 return subprocess.check_output(['git','--git-dir='+str(repo),'show',pin+':'+src],text=True)
def func(src,name):
 p=src.index('fn '+name+'(');return src[p:src.index('\n    }',p)+6]
def snapshot():
 items=blob(d,'2307e9c','src/ui/settings/catalog/items.rs');module=blob(d,'2307e9c','src/ui/settings/catalog/mod.rs')
 assert 'this.catalogs.query = state.read(cx).value().to_lowercase();' in module and 'item.matches(self.catalogs.query.trim())' in items
 index=json.loads(blob(e,'ef064381','proteus-catalog.json'))
 manifests={key:json.loads(blob(e,'ef064381','packages/'+key+'/extension.json')) for key in ['markdown-render','mermaid-render','json-render']}
 return items,index,manifests
start=dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds')
items,index,manifests=measure('read two UI files + official index + three manifests',snapshot)
def q(s):return json.dumps(s,ensure_ascii=False)
rows='\n'.join('rows.push(Entry { id:%s.into(),title:%s.into(),description:%s.into(),category:%s.into(),kind:Kind });'%tuple(q(entry[x]) for x in ['id','title','description','category']) for entry in index['entries'])
cat=','.join('Category{id:%s.into(),title:%s.into()}'%(q(c['id']),q(c['title'])) for c in index['categories'])
source="""
struct Entry { id:String,title:String,description:String,category:String,kind:Kind }
struct Kind; impl Kind { fn title(&self)->&str { "Расширение клиента" } }
struct Catalog{title:String,categories:Vec<Category>} struct Category{id:String,title:String}
struct Item<'a>{entry:&'a Entry,catalog:&'a Catalog}
impl Item<'_> { CATEGORY MATCHES }
fn main(){
 let mut rows=Vec::new();ROWS
 let catalog=Catalog{title:TITLE.into(),categories:vec![CATEGORIES]};
 for needle in std::env::args().skip(1){let query=needle.to_lowercase();let found:Vec<_>=rows.iter().map(|entry|Item{entry,catalog:&catalog}).filter(|i|i.matches(query.trim())).map(|i|i.entry.title.as_str()).collect();println!("{} => {}: {}",needle,found.len(),found.join(" | "));}
 let sample="## Проба\\n\\n| Цвет | Число |\\n| --- | ---: |\\n| Синий | 4 |";
 let html=markdown::to_html_with_options(sample,&markdown::Options::gfm()).unwrap();
 assert!(html.contains("<h2>Проба</h2>") && html.contains("<table>") && html.contains(r#"<td align="right">4</td>"#));
 println!("Offline Markdown test: heading Проба and table with numeral 4; HTML projection only.");
}
""".replace('CATEGORY MATCHES',func(items,'category')+'\n'+func(items,'matches')).replace('ROWS',rows).replace('TITLE',q(index['title'])).replace('CATEGORIES',cat)
for k,v in manifests.items():print('Manifest',k, v['title'], v['surfaces']['content'], 'Пример:', 'preview' in v['surfaces'])
with tempfile.TemporaryDirectory() as td:
 p=Path(td);f=p/'trial.rs';out=p/'trial';f.write_text(source)
 measure('rustc: extracted lookup + markdown projection',lambda:subprocess.run([rustc,'--edition=2024',f,'--extern','markdown='+str(md),'-L','dependency='+str(dep),'-o',out],check=True))
 args=['диаграмма','диаграммы','диаграммы Markdown','Markdown','Mermaid','визуализация','SVG']
 print(measure('7 queries + one Markdown conversion, fresh binary',lambda:subprocess.check_output([out,*args],text=True)),end='')
print('timed command run UTC',start,dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds'))
for k,v in stages.items():print(f'{k}: {v} ms')
