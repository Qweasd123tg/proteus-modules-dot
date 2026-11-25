# OpenCode: release response-building scratch before final acknowledgments

Clear the ordered block array, lookup map, and last-block reference after successfully building the final response. Keep the canonical response and the existing references to text, tool calls, metadata and event payloads. Failure and incomplete-stream paths remain unchanged. The production adapter uses `push` and `finish`; the now-empty builder is not available for direct reconstruction after finish.

On a 128-block synthetic stream, the actual adapter was paused at the first final acknowledgment. The old collector still held 128 array entries and 128 map entries; the patch held zero in both. The completed message and final response kept the same content and in-fixture references. The direct mixed 1,025-block check and six adapter scenarios passed, including three distinct final acknowledgment failures, non-streaming and premature EOF. Serialized callback and terminal values match modulo generated UUIDs.

This is a logical reference count, not a heap or whole-app memory result. The exact runtime modules ran in isolated Node; provider, request projection, event source and host calls used local fixtures. No native or deployed application run.
