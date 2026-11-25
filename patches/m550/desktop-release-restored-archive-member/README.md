# Desktop settings restore: release each decoded input after relocation

Keeping both the original archive member and its relocated JSON or TOML bytes until the end of restoration is unnecessary. After relocation succeeds for each member, let go of the original while retaining the relocated payload for the existing batch application. A binary member that already serves as the output is still kept by the output map. No archive streaming is introduced.

The entire archive is read and verified first as before. Member ordering, destination and relocation checks, profile processing, dry runs, backups and batch application stay unchanged. This affects the explicit archive restore command, not Desktop startup or its separate upgrade operation. See the receipt for synthetic validation and scoped Python memory observations.
