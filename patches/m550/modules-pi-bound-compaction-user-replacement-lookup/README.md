# Pi compaction: bound the latest-user replacement lookup

When preparing the compacted history, look for the latest user message once. If it is already in the removed prefix, no second lookup is needed. If it is kept, check only the removed prefix for an earlier occurrence of the same object. This preserves the prior result even when the caller uses the same message object twice.

Compaction choices, summary, model calls, checkpoint and replacement IDs remain unchanged. This is a structural change to the optional installed Pi hook, not an application benchmark.
