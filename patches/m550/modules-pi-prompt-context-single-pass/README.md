# Pi workflow: classify prompt context chunks once

Collect the first system chunk, append text and unmarked context files in one ordered pass when preparing Pi's system prompt. Preserve the first-match rule for empty and absent content, per-category order, supplied files, and the existing host/tool flow. This only changes local prompt preparation, not provider selection or context/tool authority.

Sixteen paired controls matched in four local arms on the exact owner and scoped sources. A typical five-chunk fixture, built by the local Pi adapter through an inert resource loader, went from 14 marker reads to 5 and removed both intermediate filter-result arrays. The retained prompt inputs and synthetic turn trace stayed identical. A valid synthetic deeper workspace went from 41 marker reads to 14. The output arrays still exist.

These are small structural reductions in context preparation, not throughput, process memory, Desktop startup, or a run with the real upstream SDK/provider.
