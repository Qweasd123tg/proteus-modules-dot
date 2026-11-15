# Active-pane documents proposal

Uncompiled source-only follow-up to known PR85 document-refresh.

- Read REPORT.md and DESIGN-DECISION.md for the deliberately logical, not actual-visibility, contract.
- Desktop patch applies only **after PR146 navigation-bootstrap.patch**, on Desktop 7eaf70c67dabba8595d98029c875ffc3f59209ad.
- Extensions patch applies to f82b3ad753cf397f8a931b193aa1943af1ef07a7.
- Apply only in isolated source copies for further qualification. No production application is claimed.
- Nine new Rust controls and adapted existing expectations are **NOT COMPILED / NOT RUN**. No native/wire/runtime result is claimed.
- New Files requires documents.active_panes.v1. Cached active-pane reads can continue under Settings and occlusion. Existing focused document meaning is unchanged.

The source snapshots, local reconstruction directories and raw bookkeeping are private evidence, not necessary public deliverables. The two patch files, report, design decision, checks, change summary and independent review are the reusable proposal.
