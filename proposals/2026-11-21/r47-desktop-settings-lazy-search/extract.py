"""Extract the unchanged DTOs, real built-in row catalog and complete Finder from a pinned source."""
import re
from pathlib import Path as P

def part(source, start, end):
    assert source.count(start) == 1, start
    return source[source.index(start):].split(end, 1)[0]

search = P("src/ui/settings/search.rs").read_text()
spot = P("src/ui/settings/spot.rs").read_text()
cat = P("src/settings/catalog.rs").read_text()
prefs = P("src/preferences.rs").read_text()
client = P("src/ui/settings/client.rs").read_text()
page = part(cat, '#[derive(Clone, Debug, PartialEq, Eq, Hash)]\npub enum PageId', "impl PageId")
pref = part(prefs, '#[derive(Clone, Copy, Debug, PartialEq, Eq)]\npub enum Preference', "impl Preference")
rows = part(client, "pub(super) struct RowText", "impl SettingsView")
spot_dto = part(spot, "#[derive(Clone, Debug, PartialEq, Eq)]\npub(super) struct Destination", "pub(super) struct Spot")
spot_row = part(spot, "pub(super) fn row(", "pub(super) fn model(")
spot_json = part(spot, "pub(super) fn params_json(", "pub(super) fn row(")
page_titles = [
    re.search(rf"^        PageId::{variant} => .*,$", cat, re.M).group(0)
    for variant in ("Appearance", "Chat")
]
page_title = "fn page_title(_: Option<()>, page: &PageId) -> String { match page {\n" + "\n".join(page_titles) + "\n_ => unreachable!() }}\n"
finder = part(search, "const LIMIT: usize", "/// Russian names of the pages")
row_feed = part(search, "        for (page, rows) in [", "        let place = page_title(None, &PageId::Shortcuts)")
existing_test = part(search, "    #[::core::prelude::v1::test]\n    fn exact_title", "    #[::core::prelude::v1::test]\n    fn sect") if 'fn multi_term_search' not in search else part(search, "    #[::core::prelude::v1::test]\n    fn exact_title", "    #[::core::prelude::v1::test]\n    fn section_search")
assert "let first = finder.hits.len();" in search
json_transform = part(search, "        if finder.hits.len() > first && self.is_json", "    }\n\n    fn search_addons")
json_transform = json_transform.replace("self.is_json(slot, module)", "json_mode")
P("rows.inc").write_text("{\n"+row_feed+"}\n")
P("json_transform.inc").write_text("{\n"+json_transform+"}\n")
P("tested.inc").write_text(page + pref + rows + "mod spot {\nuse super::PageId;\n" + spot_dto + spot_row + spot_json + "}\n" + page_title + finder + existing_test)
