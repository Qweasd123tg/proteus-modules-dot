# Core history-scale: avoid copying the validated snapshot again for gzip

Once the resume-idle observer has validated the session, row count, and seeded tail, it drops the decoded tree before gzip, keeping the scalar summary and original wire bytes. Write a view of the same SSE bytes after the prefix instead of creating a second full payload copy. JSON validation still runs as before. The timestamp, archived bytes, notification order, and diagnostic drain remain unchanged.

The supported legacy response can contain the entire 50,000-row transcript; the current paged format was tested with one 50-row page. Checks cover both layouts. This affects the benchmark controller, which runs outside the measured Core and module process group, not the application.

The independent synthetic responses exercise a 13,727,896-byte legacy body and a 13,905-byte paged body (50 visible rows from the same logical 50,000-message history). Each now avoids one extra Python byte slice, not all internal gzip allocations. Both archives matched byte-for-byte with a fixed header clock. Error controls cover parsing, validation, protocol readiness, and gzip open/write/close. No process memory or time was measured.

Apply `source.patch` to the pinned Core revision and exact preimage in `receipt.json`. No alternate is needed.
