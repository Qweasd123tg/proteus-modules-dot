# Native SVG benchmark: count only the two stage colors

The screenshot verifier needs the exact count of two RGB values, not a histogram of every RGB triplet. Keep the existing RGB conversion. In each tile (at most 1024 × 64), map each channel to 0 for the first target, 2 for the second, and 1 for other values. The stage targets differ in every channel; only exact first-target pixels sum to 0 and only exact second-target pixels sum to 6. Counts, thresholds, retries, settle order, and screenshot hashes stay unchanged.

Independent parity exercised 34 owned 1280 × 900 PNGs through all 16 stages and the clear step, with an inert screenshot source. The 17 saved receipt rows matched after checking each expected helper source fingerprint. Extra checks covered tile edges, PNG modes, threshold boundaries, high color cardinality, and malformed input. Compare app builds using the same capture helper version because comparison intentionally checks that fingerprint.

Four fresh helper processes per arm, run serially in ABBA+BAAB order on one logical CPU (shared host): for the 34 ordinary synthetic PNGs, median pixel-read CPU was 3.37 → 0.65 s and helper lifetime peak RSS was 24.38 → 24.81 MiB. A separate synthetic screenshot with a high-color panel went from 0.124 to 0.028 s CPU and 50.26 to 24.50 MiB peak RSS. These measurements include PNG decode and counting; they do not measure screenshot acquisition or the native app.

Apply only `source.patch` to the pinned Proteus Desktop revision in `receipt.json`. No companion patch is required.
