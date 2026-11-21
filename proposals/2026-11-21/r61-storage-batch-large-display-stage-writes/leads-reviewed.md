# R61 storage: why this experiment

- The obvious byte-budget pending-size reuse was already measured in the
  2026-11-18 SQLite-deferred negative result. It saved repeated size walks
  but not stable whole-request latency. Do not recycle it as a new patch.
- R59 counted one linear worker staged replay, 20 SDK pages and 1,251
  records, no ordinary rewind/rescan after initial placement. A resident
  seek index would not improve that route; adding one could affect error
  precedence when a temp read fails or a prefix must be authenticated.
- #256 and #362 already target raw canonical read copy/line allocation.
  #331 is separate scratch reuse on staged-read pages. #348 is derived
  cache filename reuse, not staged output. This experiment changes only
  batching of writes to the private temporary output of canonical capture.
- Keep worker source validation, temporary stage, durable catalog publish,
  flush and EOF as distinct layers. Steady replay-only large sources may
  allocate the additional bounded writer capacity without benefiting.
  Use the scope count as evidence, not phase duration, RSS, whole runtime
  speed, disk-write volume or behavior of M100/M150.
