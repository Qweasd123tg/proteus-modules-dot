# Keep distinct native history benchmark scenarios separate

Include the active model-history length when an explicit value was reported for a native Desktop run. Keep a legacy native run without that field under its old label. An explicit active length equal to the displayed length still differs from omission: the seeder writes a second compaction record.

This changes grouping in the comparison report, not the producer, sampled metrics or application.

Twenty-four actual local CLI runs on inert supplied reports verified both the pinned and cumulative sampler closures. A mixed native corpus now keeps implicit, explicit short and explicit equal active lengths separate for each cache mode. If before and after are from different scenarios, the missing side is shown as unavailable. Legacy-only Native, resume-idle and AgentControl outputs matched byte for byte.

The example values are synthetic; no native execution or performance measurement ran. The same source patch applies to both supported exact bases.
