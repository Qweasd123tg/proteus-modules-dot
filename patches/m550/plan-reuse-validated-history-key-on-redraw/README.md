# Avoid rewalking unchanged Plan history

Plan in Always mode remembers when it already checked the current session, snapshot and input generation. Later views use the same result. Changed inputs, explicit retry and cache resets still take the old validation path.

Apply `source.patch` to Extensions tree `7e95074ddfef958d2670fd51fa8b9b1b9abd3fff` or verify the exact `cache.rs` preimage. The native multi-view fixture produced 72 identical output frames and 25 matching requests, including 409/503 and recovery. On the 50,000-entry scenario the observed history-key work fell from 1,600,002 to 450,001 entry visits. This is a work count, not a speed or memory measurement.
