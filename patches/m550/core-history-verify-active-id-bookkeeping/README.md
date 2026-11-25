# Core history-scale: trim active verification ID bookkeeping

Release the full display ID set as soon as the set difference has been computed. A default run with an empty exclusion set no longer traverses each verified checkpoint or request again merely to prove that no ID belongs to that empty set. The preceding digest still reads every message ID; explicit compaction still runs the full nonempty exclusion checks.

This only changes the offline benchmark verifier. It does not change history hashes, canonical parsing, application memory or startup behavior. In a 50,000-row fixture, two requests and one checkpoint no longer made 150,005 redundant second-pass ID checks. A weak-reference witness confirms that the full display set is no longer live when decoding begins. Its shallow CPython size was 2,097,368 bytes in the fixture; this is not process RSS or heap size. Shortened histories still reject reintroduced IDs.

Apply `source.patch` to the pinned Core file, or choose the exact scoped variant from `receipt.json` if both #767 and #777 are already applied. Do not apply both:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
