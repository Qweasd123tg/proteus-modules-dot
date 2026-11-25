# Core benchmark observer: keep only needed fields in retained process rows

Keep counters and per-process high-water marks, exact identity and command-name/executable fields used by the Extensions retired-process guard, and the error map used by the private observer. Other current details, including argv and interval values, still appear in the original emitted rows, but are no longer retained for each process lifetime by the shared sampler.

The exact sampler and known consumers were checked on inert process data. The 104 plain samples and 105 paired samples on each of two private observer variants matched, including interruption recovery. The Extensions JavaScript guard still recognizes both retired synthetic processes. Across 101 plain retained identities, stored fields fell from 2,929 to 1,717. That is a structural count, not bytes, elapsed time or application memory.

No actual renderer, product or process table was sampled. This patch assumes the existing observed-row contract, not a stable full key set for arbitrary introspection of the internal retained rows.
