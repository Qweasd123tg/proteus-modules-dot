# Focused historical excerpt: read_many UTF-8 EOF

Source: [initial-modules report, section 4](https://github.com/Qweasd123tg/proteus-modules-dot/blob/b26bcd0c7de6895d12a61b6b11a3c43e6f674d0e/research/proteus-continuous-audit-2026-11-13/evidence/initial-modules/REPORT.md).

Historical Modules revision `3270dc0f894eaf4d0360306052b806099b8f5351`, Core dependency `b5fac84245b075896c24763b3aebac79b4375c2e`, dated 2026-11-12. Quoted below only for deduplication and original scope. No historical reproduction was run in this pass; no result below validates the new candidate.

## 4. read_many_files silently drops malformed UTF-8 suffix (P3, reproduced)

A six-byte file `b"valid\xc3"` returns `ok=true`, text `valid`, `original_bytes=6`, `returned_bytes=5`, and `truncated=false`. The helper meant to trim a budget-split scalar is also used when the entire file was read. Thus a genuinely incomplete final scalar is hidden instead of rejected or reported.

Source: https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/file-tools/src/read_many.rs#L250-L281

Suggested correction: use strict UTF-8 decoding when EOF is known and no budget truncation happened; trim partial scalar only at an intentional budget boundary and report truncation.
