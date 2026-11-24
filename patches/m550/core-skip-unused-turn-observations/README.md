# Core: don't capture unused before-turn model context during cold replay

One exact M391 source patch. Default ModelContextProjection still stores
the requested before-turn snapshot for committed/live callers. In strict
recovery, RemoteValidatedRead only consumes current observations, so it now
explicitly chooses current-only mode. ModelContextState::from_records also
returns only current observations from its selected prefix, so uses the
same mode. It still stops before the requested TurnOpened and clears
incomplete pending requests. Root execution tracking, filtering,
usage coalescing, interleavings, reset, compaction, typed storage integrity
and byte limits are unchanged. Storage does not negotiate a different
projection or payload. Actual projected display route is unchanged.

Final snapshots are still cloned exactly as they were. An early prototype
also moved the final Vec; that is not included because it could retain its
growth slack in the consumer, unlike the exact-length clone. Only the
unused before-turn capture has been eliminated. This is not the separate
consuming UsageProjection optimization.

## Verified scopes

Exact full 1,100-file M391 source rechecked and selector tested both
forward and reverse. Actual Rust Session Semantics 23 existing tests
(before) and 24 (after) per serde layout; the new test differentiates
committed before-turn capture from current-only projection, verifies
identical root bindings and context after subsequent changes, and verifies
the existing captured before-turn value is frozen.

Seven native paired cases per serde layout exercise the exact
RemoteValidatedRead/RemoteJournalSnapshot paths and real disposable
display staging over a local typed Storage adapter. Each ordinary scale
and mixed fixture is independently admitted through exact journal
validation. A late invalid response still fails before context application
and snapshot release is ordered the same. Valid checks cover empty, projected,
strict/nonprojecting/unsupported storage, root versus child/detached facts,
direct versus auxiliary or unknown-size failure, prefix cutoff before
a designated turn, reset and coalesced compaction markers, normal usage
and final ordered observations. Usage, display sequence hashes, result and
request order match.

Allocated bytes below are gross requests only inside
ModelContextProjection::apply on accepted TurnOpened events (the root
index is still allocated), measured natively with the same System allocator.
The existing terminal observation clone remains, with the same requested
sizes. The fixtures contain admitted typed turns, not external model calls:

| Strict fixture | Turns | Turn-opening allocation requests before → after | Calls before → after |
| --- | ---: | ---: | ---: |
| Ordinary successful root usage; final coalesced observation | 4,096 | 868,332 → 802,812 B | 4,107 → 12 allocations |
| Adversarial accepted context-window errors; growing facts | 5,000 | 200,762,812 → 802,812 B | 5,011 → 12 allocations |

The 5,000-case saving follows from exactly 4,999 deleted Vec copies:
16 × (1 + ... + 4,999) = 199,960,000 bytes, not 200 MB of live memory.
No installed-process latency, RSS or PSS measurement. No extrapolation
to the original plain-text 50,000-row fixture, which has zero context
observations. No timing claims while the independent headless build ran.

Native proof archive retained separately, SHA-256: `cfab193cd6390548f2c9b9517faf011145db4816030119ed49325d4c707fa738`.
