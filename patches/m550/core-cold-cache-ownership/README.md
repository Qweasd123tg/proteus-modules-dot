# Cold Core startup: release canonical owners between cache sections

Only `project_validated_view` consumes its canonical vectors. The canonical
messages are moved out of the local model after full validation and render,
remain available throughout conversation section writes and context summary
calculation, and are released before display page construction. Model
observations are released once their section is written. The shared borrowed
save retains its old inputs and late context summary. Both routes use the
same serializers, source binding, storage calls and publish logic. Early
summary is a local fold over committed canonical data and has no I/O; it can
now run even when a subsequent display/context/tool/HEAD stage fails.

The rendered transcript remains intact until its source-named last page is
available. Do not substitute HEAD when publication races or fails. A failed
HEAD can leave a complete named revision; missing or corrupt named bodies or
a stale write leave the original full rendered transcript unchanged. Source,
envelope, revision and journal checks do not move or weaken.

Four native Core test cases in the patch cover cache bytes and operation order
against the borrowed route; HEAD rejection with named page success;
render failure before storage saves; and stale source + missing/corrupt
named page with intact fallback. The unmodified wider Core test runner could
not build offline (103 missing locked registry entries), so do not infer a
full native Core/app pass from source-only replay or from a bounded lift.
`source-replay.json` hashes all target leaves and records strict apply/reverse
on the full exact M350 baseline and with the first two Core changes composed.

Independent bounded native source-lift: 58 controls plus two 50,000-row
projected/fallback cases per mode. Read and write order, decoded content-page
bytes, source-named header and render/fallback outputs agree with M350.
Immediately before the display section, generation-tracked requested
canonical owners total 34,088,890 to 0 bytes on default maps and 38,088,890
to 0 on preserve_order, for both projected and strict routes in the lift.
Earlier conversation phases and the subsequent named-page read are
unchanged. See independent-lift-check.json and the companion bench
source-lift artifacts for precise donor and CPU/memory caveats.

Any allocation lifetime evidence is scoped to Core and the observed write
phases. It demonstrates neither the different earlier render peak nor
695-MiB process-tree PSS, disk-cold startup speed or first frame latency.
