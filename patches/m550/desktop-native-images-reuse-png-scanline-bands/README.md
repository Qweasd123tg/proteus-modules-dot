# Desktop image benchmark: reuse identical PNG scanlines within each band

The indexed RGBA pattern depends on the row only through integer division by 16, 32 and 64. Build the filtered byte row once per aligned 16-row band, and still feed the existing zlib compressor one scanline at a time. The trailing partial band contributes exactly its original row count. Dimensions, encoder, filter byte, per-image bounds, PNG content and manifest are unchanged.

The default synthetic corpus is 16 images of 2,048 × 1,024 RGBA pixels. It needs 1,024 scanline constructions instead of 16,384, while compressing all 16,384 scanlines. All 16 PNGs and the manifest matched (only local destination paths were normalized). In eight sequential local trials (ABBA+BAAB), median preparation wall time was 1.785 s before and 0.514 s after. This measures the Python corpus generator, including fixture writes, with fresh processes and destinations on one logical CPU; it does not reserve the host exclusively. These changes affect preparation of the benchmark corpus only, not Desktop startup, rendering, or its memory.

Apply `source.patch` to the pinned Desktop image fixture.
