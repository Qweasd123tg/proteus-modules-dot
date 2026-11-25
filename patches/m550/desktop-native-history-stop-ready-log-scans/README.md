# Native-history observer: stop polling the readiness log once ready

The benchmark previously loaded and parsed the full append-only startup log on every sample, even after readiness was already known. The observer now uses the same readiness parser only while waiting for that marker. It still samples the same phases, reads the diagnostic tail on an observed process exit, and parses the complete log after teardown for the report. Events emitted during settle, idle and teardown remain in the report.

With an inert clock and an append-only fixture log, first-layout reads went from 12 to 4 and render/restart reads from 13 to 5. Phase/sample records, final late events and reports matched in those controlled cases.

This removes observer-side work, not work in Proteus itself. In a real run, doing less work between sleeps can shift observation timestamps; the sampling and readiness policies are unchanged. A post-readiness read/parse failure in an abnormal log can surface at the final parse rather than in the idle loop; parsing rules and final validation are unchanged. No real application performance or memory change is asserted.

Choose `source.patch` for the pinned Desktop file, or the exact alternate in `receipt.json` for the file with #748, #750 and #764 applied (not both):

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
