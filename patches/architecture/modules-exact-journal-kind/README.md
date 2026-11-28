# Share exact journal filename classification

Session opening and catalog cache validation use the same exact mapping
for the two canonical basenames. Other names, case variants, backup names
and invalid bytes are not recognized as journal names. No normalization,
change to journal or catalog validation, or additional read.

Use source.patch on pinned Modules or source-after-stack.patch on the
cumulative source. Verification uses only local synthetic fixtures.
