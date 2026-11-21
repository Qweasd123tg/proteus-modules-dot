"""Extract the pinned stock candidate gatherer and render's exact filter."""
from pathlib import Path
import sys

stock, output = map(Path, sys.argv[1:])
tags = (stock / "tags.rs").read_text()
editor = (stock / "tags/editor.rs").read_text()
start = tags.index("#[derive(Clone, Debug, PartialEq)]\nstruct Suggestion")
end = tags.index("fn array(", start)
gather = tags[start:end]
start = editor.index("        let query = query.to_lowercase();")
end = editor.index("        if !filtered.is_empty()", start)
filter_code = editor[start:end]
assert all(x in filter_code for x in ("suggestions(&spec.field, snapshot)", "spec\n                    .values", ".collect::<Vec<_>>()"))
filter_code = filter_code.replace("suggestions(&spec.field, snapshot)", "suggestions(field, snapshot)")
filter_code = filter_code.replace("spec\n                    .values", "selected")
output.write_text(
    '''use proteus_contracts::app_protocol::config_builder::ConfigBuilderSnapshot;
use proteus_contracts::domain::{ConfigField, ConfigSuggestions, ConfigValueSchema};
use serde_json::Value;
''' + gather + '''
pub(super) fn visible(field: &ConfigField, snapshot: Option<&ConfigBuilderSnapshot>,
                  selected: &[Value], query: &str) -> Vec<(String, String)> {
''' + filter_code + '''
    // Materialize the same first eight title/value pairs the stock
    // editor used to clone into the label and the click callback.
    filtered.iter().take(8).map(|item| (item.value.clone(), item.title.clone())).collect()
}
'''
)
