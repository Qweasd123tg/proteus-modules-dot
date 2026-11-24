# Stop sending unused history to Quota

Quota uses session state and model metadata, not entries. Its manifest now opts out of entries and keeps session events on.

Apply `source.patch` to Extensions tree `1ed0d86e935c3d34e84d3ed17dd91a8bebd103bb`. The manifest is the only change.

Both manifests selected inputs through a probe of the Desktop predicate and ran on the real Quota binary. All 21 relevant replies and five requests matched, including recovery after HTTP 503. On the synthetic 4,096-entry case, Quota received 2,790,273 fewer input bytes. No whole-Desktop time or memory measurement.
