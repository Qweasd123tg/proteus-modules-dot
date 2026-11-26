# Skip the final slot walk for a fully matching blob inventory

If every expected path was observed and none ever had the wrong
stamp, every final slot already matches. For inventories with a
disagreement, retain the stock last-observation rule. Directory walks,
filesystem metadata checks and the distinct-path cap are unchanged.

Exact Modules `5377853779ae499b03ff152b97eb1c11eaa64ed2`; full-index apply and reverse verified.
Both optimized storage-library builds passed. In each scoped native arm
116 tests passed and one was ignored. With 4,096 matching paths, the
final in-memory comparison visited 4,096 slots before and zero after.
Changing and then restoring a stamp still passed via the original
4,096-slot path. The matcher agreed with last-write-wins map equality
across 9,331 exhaustive short traces. No latency or RAM number is inferred.
