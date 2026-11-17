"""Read public source/JSON only. No Desktop, add-on, network or installation actions."""
import json
import re
import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: python3 verify_catalog_ui.py DESKTOP_TREE MODULES_TREE EXTENSIONS_TREE")

desktop, modules, ext = map(Path, sys.argv[1:])
def read(name):
    return (desktop / name).read_text(encoding="utf-8")
def get_catalog(root):
    return json.loads((root / "proteus-catalog.json").read_text(encoding="utf-8"))["entries"]
def items_in(name, text):
    found = re.search(name, text, flags=re.M | re.S)
    if not found:
        raise SystemExit("Source no longer matches: " + name)
    return found.group(1)

schema = read("src/catalog/schema.rs")
entry = items_in(r"#\[serde\(deny_unknown_fields\)\]\s+pub struct Entry \{(.*?)\n\}", schema)
fields = re.findall(r"^    pub (\w+):", entry, flags=re.M)
assert fields == ["id", "kind", "title", "description", "category", "version", "path", "source"]
kinds = re.findall(r"^    (\w+),", items_in(r"pub enum Kind \{(.*?)\n\}", schema), flags=re.M)
assert kinds == ["ProcessModule","ClientExtension","AgentPlugin","Skill","McpServer"]
prefix = "src/ui/settings/catalog/"
state, items, view, overview, details, keys = [read(prefix + n + ".rs") for n in ["mod","items","view","overview","details","keys"]]
assert "show: Show::Overview" in state and "self.catalog_overview(&items" in view
assert "Some(package) if package.problem.is_some() => Status::Broken" in items
assert "if !install::connected(old, &self.baseline) => Status::Detached" in items
overview_states = tuple(re.findall(r"pick\(Status::(\w+)\)", items))
installed_filter = items_in(r"Show::Installed => matches!\(\s*item.status,\s*(.*?)\s*\),", items)
installed_states = tuple(re.findall(r"Status::(\w+)", installed_filter))
assert overview_states == ("Update","Installed") and installed_states == ("Installed","Update","Broken")
assert "if sections.is_empty()" in overview and 'Ничего не установлено.' in overview
labels = dict(re.findall(r'Status::(\w+) => "([^"]+)"', view))
assert 'Status::Installed => {' in view and '.child("Установлено")' in view
labels["Installed"] = "Установлено"
assert labels == {"Available":"Установить","Detached":"Подключить","Update":"Обновить","Broken":"Переустановить","Installed":"Установлено"}
assert 'this.install_catalog_entry(source.clone(), entry.clone(), cx)' in view
assert 'item.entry.id == id && item.status != Status::Installed' in keys
assert 'После установки выберите инструменты или реализацию слота в профиле.' in details
assert 'Для сборки: {}' in details
ms, xs = get_catalog(modules), get_catalog(ext)
mem = {e["id"]:e for e in ms if e["id"] in ("memory-pack","sqlite-memory")}
assert set(mem)=={"memory-pack","sqlite-memory"}
for key, export in [("memory-pack","jsonl_memory"),("sqlite-memory","sqlite_memory")]:
    v = mem[key]
    assert v["kind"] == "process_module"
    assert "context_provider/"+export in v["description"] and "tool/"+export in v["description"]
assert len(xs)==14 and all(e['kind']=='client_extension' for e in xs)
assert all(not re.search('memory|памят',e['id']+' '+e['title']+' '+e['description'],re.I) for e in xs)
result={
    "basis":"Text predicates and official JSON only; no UI event or package execution.",
    "trace_preconditions":"One loaded matching, installable (not source-only) entry, no search or facet, initial overview, no operation in progress. Listed action labels are not a promise that a button is enabled.",
    "desktop_catalog_entry_fields":fields,"desktop_catalog_kinds":kinds,
    "one_item_default_overview_trace":[{"given":s,"shown_in_overview_rows":s in overview_states,"shown_in_installed_filter":s in installed_states,"row_action_or_label":labels[s]} for s in ["Available","Broken","Detached","Update","Installed"]],
    "two_alternative_modules":[{"id":k,"catalog_description":mem[k]["description"]}for k in sorted(mem)],
    "official_desktop_entries":len(xs),"entries_named_or_described_as_memory":0,
}
print(json.dumps(result,ensure_ascii=False,indent=2))
