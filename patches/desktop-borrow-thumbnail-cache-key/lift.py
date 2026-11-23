"""Lift the exact production Slot, SentImages and LRU; only external project boundaries are modeled."""
from pathlib import Path
import sys

images, cache, tests, cases, output = map(Path, sys.argv[1:])
source = images.read_text()
lru = cache.read_text()
donors = tests.read_text()

def region(body, start, end):
    assert body.count(start) == body.count(end) == 1, (start, end)
    first = body.index(start)
    last = body.index(end)
    assert first < last
    return body[first:last]

owners = region(source, "#[derive(Clone, Debug, PartialEq, Eq)]\nstruct Key", "#[derive(Default)]\nstruct Shared")
sent = region(source, "thread_local! {\n    static SHARED:", "impl Chat {\n")
# First upstream test (tickets) and the four pure reconnect fixtures. Do not
# lift native GPU image helpers or the GPUI pump test; these need native deps.
upstream = donors[donors.index("#[::core::prelude::v1::test]"):donors.index("#[::core::prelude::v1::test]\nfn cache_eviction")]
upstream += donors[donors.index("fn retry_slot("):donors.index("#[::core::prelude::v1::test]\nfn only_connected")]
upstream = upstream.replace("#[::core::prelude::v1::test]\n", "")
template = cases.read_text()
for marker, content in {
    "// @OWNERS@": owners,
    "// @SENT_IMAGES@": sent,
    "// @LRU@": lru,
    "// @UPSTREAM_TESTS@": upstream,
}.items():
    assert template.count(marker) == 1
    template = template.replace(marker, content)
output.write_text(template)
