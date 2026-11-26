# Encode image bytes directly into the data URL

Use the same validated local file read, and append padded base64 directly
to a correctly sized URI buffer instead of creating a second full string.
Anthropic's plain base64 output and all size/MIME diagnostics are unchanged.

Apply on Modules `4fa39c3ce94119e36f3ff4a86e28dd2171342aba`. No alternate is needed.

Both unmasked optimized libraries built. 13 focused tests
passed on each arm. Owned local synthetic images check exact complete URLs,
padded base64, size/MIME/missing negatives and the unchanged raw encoder.
At the 5 MiB accepted limit, the URI helper made 4
→ 2 allocator/reallocator requests,
requesting 6990534 fewer bytes in aggregate. This is allocator traffic
inside the helper, not process peak memory or timing.
