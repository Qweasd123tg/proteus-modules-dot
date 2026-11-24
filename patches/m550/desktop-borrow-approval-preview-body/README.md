# Desktop: avoid copying an approval card body before clipping

A selected approval card now reads the preview or raw string subject directly from its request. It still gives the full-text dialog an owned string, so the text and Copy action remain available after the request drops. Formatted fallback JSON and approval controls are unchanged.

In the scoped native check, all 24 cases, 192 allocation ledgers and 24 lifetime controls matched. For a 2 MiB body, preparing the preview and full-text capture reduced peak requested heap from 4,206,320 to 2,109,168 bytes with the same retained output. This is not an app-memory, GPU, timing or approval-policy benchmark.

The change applies and reverses as an exact hunk on the verified owner revision. Compose with #681 to reproduce the entire measured source file.
