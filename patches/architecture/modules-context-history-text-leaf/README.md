# Modules: break two context compaction dependency cycles

History reconstruction and token budgeting now share a private text projection with the summary path. The five existing helper bodies and summary prefix bytes are unchanged. History still owns which messages are retained, budget still owns truncation, and summary still owns the request, response and cancellation.

Apply `source.patch` to Proteus-harness/Proteus-modules at `7274147162cb226f05df13a52b4a271fa5619313`. The same patch applies on the checked cumulative Modules tree. Native tests use only canned model responses.
