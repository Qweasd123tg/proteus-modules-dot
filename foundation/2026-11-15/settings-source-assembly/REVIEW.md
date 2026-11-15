# Independent exact source review

Scope: existing Desktop settings proposals #134 JSON Args/Env, #135 receipt switch semantics and #136 accepted-profile revision, assembled on Desktop `7eaf70c67dabba8595d98029c875ffc3f59209ad`. The actual contracts pin remains `41bdfffa6e70228278b4abc758b7f81a12672f35`. No new production implementation or migration policy was introduced by this pass.

## Preliminary review

The independent reviewer identified three required junctions: invalid/same-value JSON must remain visible to edit_revision; receipt equality must not weaken ACK rebase conflict equality; every accepted snapshot including catalog ACK and value-equal acceptance must advance profile_revision. It also required preservation of the explicit JSON UX break, single-flight initial loading and the distinction between raw edits and accepted snapshots.

## Exact verdict

The reviewer accepted the exact source-only composition with no new blockers found at the inspected junctions:

- Invalid/same-value MCP JSON input reaches update_draft and increments edit_revision even without a typed draft change.
- Duplicate decoded Env keys and trailing input are rejected before replacing the typed value.
- The receipt comparator excludes only enabled; ACK rebase remains unchanged and uses complete comparison.
- Catalog ACK reaches accept_save/accept_baseline and advances profile_revision.
- Accepted-profile epoch changes suppress old read successes/errors; raw-edit revision suppresses successful replacement only.
- Single-flight admission includes initial load.
- The report correctly limits all-six-order text composition, 24 proposed new tests and two existing fixture adaptations to source evidence; no native/HTTP scenario is claimed executed.
- The combined patch is an alternative to the selected originals. The historical !reloading Save guard is not included.

After exact review, the report's opening execution disclaimer was clarified to name actual catalog installation and application/MCP processes, rather than the ambiguous word “process.” The reviewer reread the correction, confirmed no new blocker and the final identity below. System patch application is explicitly recorded separately in the report.

Final reviewed SHA256:

- `composed-settings.patch`: `8051d019d6d2371e20fd7c03589b9e6e3b2ee63433f4dd5a68d7dcc9a1d0e398`
- `REPORT.md`: `31aa5986d0dfebcd8522b9e82d0b5fc427ac7c5ddc460b9a729ca181d2aa0284`

The reviewer read source, metadata/logs and computed hashes only. It made no edits, published nothing and ran no project code, tests, fixtures or runtime. Security/process/excluded investigations were not expanded. Acceptance does not establish Rust compilation, native scheduling, real profile persistence, full settings race closure or production readiness.
