"""Independent expected height and synthetic corpus for actual Rust old/new functions."""
from itertools import product
from random import Random

BREAKS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def spec(body, wrap):
    lines = body.splitlines()  # excludes a final empty row; CRLF is one separator
    rows = sum(max(1, (len(line) + 109) // 110) for line in lines) if wrap else len(lines)
    return min(360, max(48, max(1, rows) * 18 + 16))


def fixture_bodies():
    for k in range(8):
        for chars in product("A\r\n\u2028", repeat=k):
            yield "".join(chars)
    for sep in [*BREAKS, "\r\n"]:
        for n in (0, 1, 2, 3, 18, 19, 20, 21, 47):
            for width in (0, 1, 109, 110, 111, 219, 220, 221):
                for end in ("", sep):
                    yield sep.join(["🦀" * width] * n) + end
    rng = Random(20261119)
    for _ in range(1000):
        yield "".join(rng.choice(("A", "界" * 110, "👨\u200d👩", "\r\n", *BREAKS, "🦀" * 113))
                        for _ in range(rng.randrange(130)))
    # Maximum UTF-8 density per old visual row and truncation inside CRLF/scalars.
    for size in (109, 110, 111):
        for n in (18, 19, 20, 21):
            for head in ("", "a", "ab", "abc"):
                for tail in ("", "\r", "\r\n", "🦀" * 5000):
                    yield head + ("🦀" * size + "\r\n") * n + tail
