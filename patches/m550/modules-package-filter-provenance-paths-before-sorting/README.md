# Modules packaging: filter provenance names before sorting paths

Select the existing exact provenance basenames from the same directory walk before sorting. Run the original file check on every candidate and copy the same files in the same relative order. Package hashes, output validation, staging, rollback and archive publication are unchanged. Directory traversal still runs; this avoids the explicit file checks and sort entries for unrelated names, not a measured number of disk operations.

The package checks reconstruct the pinned source-tree topology with inert local files and compare the actual Python install/archive paths. Across the 20 reconstructed packages, both the explicit source file checks and the number of paths entering the sort went from 408 to 10; the traversal still yielded 408 paths and the same 10 provenance entries were copied. No executable or Cargo build is run. An incidental file-status error for a path that cannot be packaged is no longer observed; status and copy errors for eligible paths are still checked.

Apply `source.patch` on the exact pinned Modules revision or use the embedded variant in `receipt.json` if #775 is applied. Do not apply both:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
