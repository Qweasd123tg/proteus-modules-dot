#!/usr/bin/env python3
"""Run only the four native GUI preparation arms, retained action methods, and captured payload in an offline, synthetic recorder."""
import argparse, subprocess as sp, tempfile
from pathlib import Path
p=argparse.ArgumentParser()
for arg in ('desktop','rustc','serde-json'): p.add_argument('--'+arg,required=True)
p.add_argument('--ref',default='2307e9c67125bbe66f15ced51317a2dfcc437aa4')
p.add_argument('--patch',type=Path,default=Path(__file__).resolve().parent.parent/'retain-current-widget-action.patch')
args=p.parse_args()
base='src/ui/extensions/declarative'
def upstream(f):return sp.check_output(['git','--git-dir',args.desktop,'show',args.ref+':'+base+'/'+f+'.rs'],text=True)
def func(t,n):
 start=t.index(n+'(')
 end=t.index('\n    }',start)+6
 return t[start:end]
def arm(t,n):
 start=t.index('            Node::'+n+' {', t.index('fn prepare_fields_in('))
 end=t.index('\n            }\n',t.index('=> {',start))+14
 return t[start:end]
def run(src,folder):
 fields=src('fields')
 modern='struct WidgetAction {' in fields
 s=Path(__file__).with_name('collector.rs.in').read_text()
 def sub(k,value):
  nonlocal s
  assert k in s,k
  s=s.replace(k,value)
 sub('@@arms@@','\n'.join(arm(fields,k) for k in ['Graph','Tree','Lanes','List']))
 sub('@@sender@@',func(fields,'fn widget_action' if modern else 'fn row_sender'))
 sub('@@rows_act@@',func(src('rows'),'fn act_at')); sub('@@tree_act@@',func(src('tree'),'fn act_at'))
 graph=src('graph');click=next(l.strip() for l in graph.splitlines() if 'select.clone(),' in l and ('this.selected' in l or 'this.action.' in l)) if not modern else next(l.strip() for l in graph.splitlines() if 'this.action.emit(' in l)
 assert '(node.id.clone(), node.id.clone())' in graph;sub('@@graph_click@@',click)
 for k,plural in [('List','lists'),('Lanes','lanes'),('Tree','trees'),('Graph','graphs')]:
  render=src('render');ix=render.index('Node::'+k+' { id, .. } => div()');assert 'self.fields.'+plural+'.get(id).cloned()' in render[ix:ix+180]
 for k in ['list','lanes']:sub('@@'+k+'_clicked@@',func(src(k),'fn clicked'))
 assert 'self.act_at(self.cursor, "open", cx);' in src('rows') and 'K::clicked(event.click_count())' in src('rows')
 assert 'this.act_at(index, "check", cx);' in src('tree_row') and 'this.act_at(index, "select", cx)' in src('tree_row')
 assert 'self.act("open", cx);' in src('tree')
 if modern:
  bind=fields[fields.index('pub(super) struct WidgetAction'):fields.index('pub(super) enum Text')]
  sub('mod ui {\n use super::*;', 'mod ui {\n use super::*;\n'+bind); sub('use ui::View;', 'use ui::{View,WidgetAction};')
  sub("action:impl Fn(String,&'static str,&mut App)+'static","action:WidgetAction")
  sub('action:RowAction','action:WidgetAction'); sub('action:Rc::new(action)','action')
  sub('selected:Rc<dyn Fn(String,&mut App)>','pub(super) action:WidgetAction')
  sub("selected:impl Fn(String,&mut App)+'static","action:WidgetAction"); sub("selected:Rc::new(selected)","action")
  for k in ['rows','tree','graph']:
   assert 'pub(super) action: WidgetAction' in src(k)
   assert '\n            action,\n' in src(k)
 else:
  for k in ['rows','tree']:assert 'action: Rc::new(action)' in src(k)
  assert 'selected: Rc::new(selected)' in graph
 f=folder/'peer.rs';f.write_text(s);lib=Path(args.serde_json)
 sp.run([args.rustc,'--edition','2021',str(f),'--extern','serde_json='+str(lib),'-L','dependency='+str(lib.parent),'-o',str(folder/'peer')],check=True)
 return sp.run([folder/'peer']).returncode
with tempfile.TemporaryDirectory() as d:
 d=Path(d);code=d/base;code.mkdir(parents=True)
 for f in ('fields','tree','rows','graph','render','tree_row','list','lanes'):(code/(f+'.rs')).write_text(upstream(f))
 local=lambda f:(code/(f+'.rs')).read_text()
 print('BASE',flush=True);red=run(local,d)
 print('CANDIDATE',flush=True);sp.run(['git','apply','--check',str(args.patch.resolve())],cwd=d,check=True);sp.run(['git','apply',str(args.patch.resolve())],cwd=d,check=True)
 green=run(local,d);sp.run(['git','apply','--reverse','--check',str(args.patch.resolve())],cwd=d,check=True)
 if (red,green)!=(1,0):raise RuntimeError(f'unexpected red/green exits {red}/{green}')
 print('expected red/green exits = 1/0; forward/reverse applicability clean')
