"""Use the stock sidebar's exact grouping and reveal order as the baseline."""
from pathlib import Path
import sys

source, destination = map(Path, sys.argv[1:])
text = source.read_text()
start = text.index("            let short = |ix: usize, row: &Row|")
end = text.index("            let has_more", start)
code = text[start:end]
assert code.count("rows(") == 2
code = code.replace("rows(&every, true, target, slot);", "every.into_iter().for_each(&mut show);")
code = code.replace("rows(&first, true, target, slot);", "first.into_iter().for_each(&mut show);")
assert "rows(" not in code
assert "let hidden = if all { 0 } else { rest.len() };" in text
assert "rows(&rest, true, &mut extra," in text
destination.write_text(
    '''use crate::sessions::Row;
use proteus_tabs::ChatKey;

const PROJECT_ROWS: usize = 5;

pub(super) fn visit<'r, 's>(
    project: &'r crate::sessions::Project<'s>,
    current: Option<&ChatKey>,
    all: bool,
    more_moving: bool,
    mut show: impl FnMut(&'r Row<'s>),
) -> (usize, Vec<&'r Row<'s>>) {
''' + code.replace("current.as_ref()", "current") + '''
    let hidden = if all { 0 } else { rest.len() };
    (hidden, if more_moving { rest } else { Vec::new() })
}
'''
)
