# Render a single model answer without joining it again

In the Analysis extension’s model-step detail, a single recorded response message can go straight to the answer disclosure. Empty and multiple-message responses keep the original fallback and separators. The same rule covers responses recovered from a partial result or a failed request.

The full model-detail builder returned byte-identical JSON in all 17 synthetic cases (68 paired native calls). On a 2 MiB singleton answer, each of the three source-selection routes reduced peak and gross requested allocation by 2,097,176 bytes, with the same retained bytes. This is a scoped allocation measurement, not full worker or Desktop memory, PSS, or latency.
