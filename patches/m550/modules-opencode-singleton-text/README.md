# OpenCode: avoid collecting and joining a lone text part

A plain one-part canonical message containing a string Text now returns that string directly. The original fallback remains unchanged for all other shapes, including mixed parts and unsupported diagnostics. No trimming or image-validation change.

The actual local nativeContext projection and compaction summary callback were exercised with synthetic inputs and an inert upstream driver. All 17 projection pairs and seven summary callback pairs matched. In a separate structural probe with 4,096 qualifying rows, the full projected context was identical while the per-message collector join dropped from 4,096 calls to zero. This is not a product memory or startup benchmark.

The patch targets pinned Modules; the receipt includes the exact isolated leaf and the equivalent scoped variant after #741, #745 and #746.
