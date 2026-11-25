# OpenCode initial context: skip the unused instruction delta

Initial-context construction reads and encodes the same instruction sources and renders the same ordered values. It only needs the native availability error from the old delta calculation. When an actual unavailable sentinel is present, the original `Instructions.diff` still runs, producing its original ordered keys and error. For a bounded set of the expected built-in scalar and instruction-file values, the successful branch yields a no-op instead of building and discarding canonical JSON hashes, a delta and a blob map. Other shapes and observations beyond 64 instruction files or 256 Ki UTF-16 code units still use the exact original diff path; the optimization bound is not a new input limit.

Validation uses the exact Modules adapter and authenticated OpenCode 2.0.22 instruction logic with real Node SHA-256 and inert local Effect/filesystem seams. Instruction reads, rendering and authorization checks are unchanged. The five-file ordinary-shaped test removed three SHA-256 calls over 109,892 UTF-8 bytes of canonical inputs; rendered output and errors matched. Oversized and unexpected cases executed the original path. This is not an installed-SDK scheduling, cold start, or application memory measurement.

Apply `source.patch` to the pinned Modules revision.
