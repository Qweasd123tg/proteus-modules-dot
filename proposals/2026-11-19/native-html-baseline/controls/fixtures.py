"""Deterministic synthetic assistant Markdown. Prefix byte cuts round down to UTF-8."""
from pathlib import Path
import sys


def make():
    style = [
        "Измерь время ответа на коротком запросе, затем сравни с длинным.",
        "Сверь результат с исходной таблицей и сохрани порядок при равенстве.",
        "При новом вводе нужно обработать текущую ревизию, а не старую.",
    ]
    parts = [
        f"### Проверка {i + 1}\n\n{style[i % len(style)]} Для шага **{i + 1}** "
        f"сохрани значение `row_{i + 1}`. Подробнее: [отчёт](https://example.org/result/{i + 1}).\n\n"
        for i in range(220)
    ]
    prose = "".join(parts).encode()[:53762].decode(errors="ignore")
    # A closing definition changes the markup of the first paragraph retroactively.
    refs = "Проверка: [отчёт][verify].\n\n" + prose + "\n\n[verify]: https://example.org/late-destination\n"
    return {"prose": prose, "late-ref": refs}


if __name__ == "__main__":
    dest = Path(sys.argv[1])
    dest.mkdir(parents=True, exist_ok=True)
    for name, value in make().items():
        (dest / f"{name}.md").write_text(value)
