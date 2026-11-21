from pathlib import Path
import sys

root=Path(sys.argv[1])
def edit(path, f):
    path=root/path
    old=path.read_text()
    path.write_text(f(old))

chat=Path('src/ui/chat')
def history(src):
    head=src[:src.index('\nimpl Chat {')]
    head=head.replace('use super::Chat;\n','').replace('use gpui_kit::*;\n','').replace('mod height_key;\n','')
    return head+'\n#[cfg(test)]\nmod tests;\npub(crate) mod diagnostic;\n'
edit(chat/'history.rs', history)
def context(src):
    head=src[:src.index('\nimpl Chat {')]
    head=head.replace('CACHE_ROWS, Chat, Direction','CACHE_ROWS, Direction').replace('use gpui_kit::*;\n','')
    name='    fn accepted_remote_seek_event_starts_context_resolution_and_failed_loading_finishes_at_row_start()'
    at=head.index(name)
    test=head.rfind('    #[::core::prelude::v1::test]',0,at)
    end=head.index('\n    }\n}',at)+7
    assert 'gpui::TestAppContext' in head[test:end]
    head=head[:test]+head[end:]
    return head
edit(chat/'history/context.rs',context)
def excerpt(source,anchor,derive=False):
    text=(root/source).read_text()
    start=text.index(anchor)
    end=text.index('\n}\n',start)+3
    if derive:
        start=text.rfind('#[derive(',0,start)
    return text[start:end]
(root/chat/'stamp.rs').write_text('use crate::transcript::Entry;\n'+excerpt(chat/'stamp.rs','pub(super) fn hidden('))
source=chat/'scroller/scrollbar.rs'
(root/chat/'scroller.rs').write_text(excerpt(source,'pub(crate) struct HistoryRange',True)+excerpt(source,'pub(crate) struct ScrollTarget',True))
(root/'src/ui/mod.rs').write_text('pub(crate) mod chat;\n')
(root/chat/'mod.rs').write_text('pub(crate) mod history;\nmod row_layout;\nmod stamp;\nmod scroller;\n')
(root/'src/agents/codex/mod.rs').write_text('mod types;\npub use types::{Item, ItemKind};\n')

def history_tests(src):
    for name in ("overlapping_live_tail_keeps_older_visible_rows_until_the_anchor_reaches_live",
                 "returning_to_live_tail_keeps_gpui_logical_anchor_and_unique_row_keys"):
        start=src.index(f'#[test]\nfn {name}(')
        end=src.index('\n}\n',start)+3
        assert 'gpui_kit::' in src[start:end]
        src=src[:start]+src[end:]
    assert 'gpui_kit::' not in src
    return src
edit(chat/'history/tests.rs',history_tests)

def instrument_text(src):
    plain='text: message.text.into(),'
    reuse='text: shared_text.unwrap_or_else(|| message.text.into()),'
    if reuse in src:
        assert src.count(reuse)==1
        return src.replace(reuse, 'text: shared_text.unwrap_or_else(|| crate::ledger::text(message.text)),')
    assert src.count(plain)==1
    return src.replace(plain, 'text: crate::ledger::text(message.text),')
edit(Path('src/transcript/mod.rs'), instrument_text)
