# OpenCode workflow: gather final reply fragments directly

Collect the latest reply's text fragments into one list, in their original order, before joining them with the same separator. This avoids allocating intermediate flat-map lists for each message and part. An empty latest reply still replaces the previous text.

Text is still assembled after the same history checkpoint. This patch does not change the model, tools, permissions, events or the checkpoint itself. The receipt describes the bounded projection proof, not an application benchmark.
