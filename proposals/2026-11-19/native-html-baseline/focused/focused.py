"""Run original function bodies from state.rs (not the upstream macro/libtest runner).
     python3 focused.py /path/to/pinned/Proteus-desktop /path/to/fresh/workdir /path/to/defer-rich-text-only.patch
Optional CARGO_TARGET_DIR shares build artifacts, CARGO_NET_OFFLINE=true uses cached packages.
"""
import hashlib,os,sys,subprocess,shutil,re,json
from pathlib import Path
src=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
f=src/'vendor/gpui-base/src/text/state.rs';body=f.read_bytes()
assert hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()=='a590e391d4ffa62076ee66e91e5cf6bcda530817'
base=body.decode();here=Path(__file__).resolve().parent
patch=Path(sys.argv[3]).resolve();assert hashlib.sha256(patch.read_bytes()).hexdigest()=='a5bd0504829a4f3716c81928ca54a8fa1d48a26145c17807434926bbe9f1d6e6'
host=Path('src/ui/extensions/declarative/rich_text.rs')
(out/host.parent).mkdir(parents=True,exist_ok=True);shutil.copyfile(src/host,out/host)

names=['set_text_then_push_str_appends_to_replaced_content','full_parse_coalesced_with_append_preserves_new_select_all','set_text_extending_markdown_appends_and_keeps_selection','set_text_streaming_markdown_matches_a_full_parse','set_text_extending_html_parses_it_again','set_text_extending_after_a_parse_error_parses_it_again','set_markdown_extensions_reparses_existing_text','update_options_merge_keeps_latest_full_text','append_merged_into_async_replace_remains_a_replacement','update_future_yields_before_coalescing_all_queued_updates']
def fn(name):
    # These ten functions + helper have no earlier line indented exactly four
    # spaces closing a nested expression; marker is their literal closing brace.
    at=base.index('    fn '+name+'(');end=base.index('\n    }\n',at)+6
    return base[at:end]
p=out/'vendor/gpui-base';shutil.copytree(src/'vendor/gpui-base',p,dirs_exist_ok=True)
subprocess.run(['git','apply','--check',patch],cwd=out,check=True)
subprocess.run(['git','apply',patch],cwd=out,check=True)
content='\nmod r5_original_cases {\n    use super::*;\n    use gpui::{Entity, TestAppContext, TestDispatcher};\n    use crate::text::{MarkdownNode,node::Span};\n'
notes={}
for name in ['parsed_blocks',*names]:
    text=fn(name);content+=text+'\n';notes[name]=hashlib.sha256(text.encode()).hexdigest()
opt_name='opted_set_text_extending_html_parses_it_again'
opt=fn('set_text_extending_html_parses_it_again').replace('fn set_text_extending_html_parses_it_again(', 'fn '+opt_name+'(',1).replace('TextViewState::html(', 'TextViewState::html_for_replacements(')
content+=opt+'\n'+(here/'late-push.rs').read_text()
content+='\n    impl TextViewState { pub fn run_pinned_tests() {\n'
for name in names:
    if 'cx: &mut TestAppContext' in fn(name).partition('{')[0]:
        call=f'{name}(&mut TestAppContext::build(TestDispatcher::new(0), Some("{name}")))'
    else:call=f'{name}()'
    content+=f'      {call}; println!("PASS {name}");\n'
for name in [opt_name,'opted_late_push_keeps_fragment_semantics']:
    content+=f'      {name}(&mut TestAppContext::build(TestDispatcher::new(0), Some("{name}"))); println!("PASS {name}");\n'
content+='    } }\n}\n'
with (p/'src/text/state.rs').open('a') as fh:fh.write(content)
(out/'body-sha256.json').write_text(json.dumps(notes,indent=2)+'\n')
cargo=f'''[package]
name = "scoped-state-test-bodies"
version = "0.1.0"
edition = "2024"
[dependencies]
gpui-base = {{path = "vendor/gpui-base", features=["gpui-fast","test-support"]}}
[patch.crates-io]
gpui-fast = {{path = "{src}/vendor/gpui-fast"}}
'''
(out/'Cargo.toml').write_text(cargo)
shutil.copyfile(src/'Cargo.lock',out/'Cargo.lock')
(out/'src').mkdir(exist_ok=True);(out/'src/main.rs').write_text('fn main() { gpui_base::text::TextViewState::run_pinned_tests(); }\n')
subprocess.run(['cargo','run'],cwd=out,check=True)
