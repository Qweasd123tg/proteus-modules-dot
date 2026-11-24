# Compare a fresh task anchor without joining text first

On a fresh workflow turn, compare the canonical User text parts directly with the task text. Keep the exact two-newline separator between text parts, including empty parts, and ignore the same nontext parts. Role, continuation bypass, error messages, anchor selection and state/persistence behavior stay unchanged.

The isolated default-layout Rust check used actual pinned canonical DTOs, the exact condition/error construction and the original or replacement helper. It passed 18 fixtures × four ABBA arms, all 72 success/error results exact. Retained requested allocations match. In the synthetic 2MiB single-part case peak went 2,097,216→0 B; in the split-part case 2,097,218→0 B. The large continuation/non-User negative controls were unchanged. This is a temporary allocation in the text comparison, not whole-turn memory, timing or a workflow/process run. Input fixture construction is outside the meter.

One source leaf; independent strict direct forward/inverse on owner Modules main and actual package pin, no earlier patch required.
