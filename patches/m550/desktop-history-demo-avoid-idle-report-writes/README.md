# Native history demo: write the reports when their contents change

The interactive history demo periodically rewrote the full trace and state even if no new trace rows had arrived. Only this demo now compares its current status and append-only trace length with the last report's pre-write stamp. It still writes the first report, the READY transition, any new history events, and the final report on normal or existing failure exits. An append between the check and write may cause one extra follow-up. The pipe, history paging, and deadlines are unchanged.

The files are reports, not a modification-time heartbeat. An unchanged poll now performs no write, so it does not incidentally detect new write errors on that poll. The shared reporter and other demo runners keep their original policies.

In a controlled 605-poll scenario with three page requests, scheduled reports went from 606 to 5 pairs (1,212 to 10 file replacements, including finalization). Visible reports and wire responses matched after verifying their actual source fingerprints. This was a deterministic test with an inert child, not a measurement of Desktop CPU, latency, or memory.

Apply `source.patch` to the pinned Desktop revision in `receipt.json`; no alternate needed.
