"""Learning sample: pure panel state and a widget tree; no Desktop entry point or I/O."""
from dataclasses import dataclass

ITEMS = (("Заметка о липе", "Черновик"), ("Список покупок", "Готово"), ("Липовый чай", "Готово"))

@dataclass(frozen=True)
class Panel:
    query: str = ""

    def apply(self, action, value):
        if action == "filter" and isinstance(value, str):
            return Panel(query=value)
        return self

    def root(self):
        needle = self.query.strip().casefold()
        rows = [list(item) for item in ITEMS if needle in item[0].casefold()]
        results = ({"type": "table", "columns": ["Название", "Статус"], "rows": rows}
                   if rows else {"type": "text", "text": "Совпадений нет"})
        return {"type": "stack", "children": [
            {"type": "bar", "children": [
                {"type": "input", "id": "name-filter", "search": True,
                 "value": self.query, "placeholder": "Название", "action": "filter"}]},
            results]}
