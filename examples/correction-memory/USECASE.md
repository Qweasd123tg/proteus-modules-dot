# Runnable authored use case (implemented, unrun)

The intended consumer is an agent maintaining **proposed** release-status notes,
not an automatic truth store. All paths below belong to a disposable workspace;
there is no migration of existing user memory.

Operator setup:

- create an empty private `correction-store/` directory;
- configure `evidence.verify_spans` source `release-note` → `evidence/release.txt`;
- supply that verifier's full config digest to the correction module;
- enable the four named memory tools and verifier/reader under normal host policy;
- allow reads only for these owned artifacts; require explicit writes approval.

Owned text artifact:

```text
channel=draft
publish=false
```

Its exact bytes/hash and quote offsets are generated from the authored fixture,
not inferred from these rendered Markdown lines.

1. Invoke `memory.correction_init {}` under WritesFiles approval. Capture the
   database instance ID. An earlier module load/list must not have created it.
2. Read entry `release.status`: absent, revision 0.
3. Prepare proposal A, text `Release remains draft.`, quoting `channel=draft`.
   The prepare tool reads revision 0 and invokes the real evidence verifier.
4. Independently prepare proposal B for the same key/revision, e.g. `Do not
   publish this release.`, quoting `publish=false`. No reservation was made.
5. Apply A with operation ID `op-release-1` and normal host write approval.
   The apply tool verifies evidence again, then atomically commits revision 1
   and the durable outcome for that ID.
6. Apply B with `op-release-2`: conflict expected0/observed1; revision stays1.
   The conflict result is itself durably replayable and does not mean B's text
   or evidence was false.
7. Retry exactly A/`op-release-1`, including after worker restart: same stable
   outcome, no revision increment and no new verifier callback on this already
   durable fast path. It is historical evidence, not a freshness check.
8. Change A's text but reuse `op-release-1`: operation_payload_mismatch, no write.
9. Read current entry and its evidence observation. Prepare a new replacement
   against revision1 and use a fresh ID for an intentional later correction.

A concurrent independent writer can invalidate the revision observed by prepare;
that is why the conditional comparison occurs in SQLite's write transaction.
Source text can also change between verification and commit: the committed note
retains the observed hash/quotes and `semantic_entailment=not_evaluated`, not a
claim that the artifact was locked or that the proposed prose follows from it.

`cargo run --locked --example correction_workflow` runs both actual modules with
a deliberately authored in-process callback router/reader and a newly created
temporary artifact/database. It captures typed results, nested verifier/read call
IDs, revisions and stable outcomes, and asserts positive/replay/conflict/changed-
payload controls before printing JSON. It does **not** exercise Core approval,
canonical journaling or the official read_file implementation. There is no runtime
result yet. A future real-Core runner must separately demonstrate those host seams;
exit status alone is not that evidence.
