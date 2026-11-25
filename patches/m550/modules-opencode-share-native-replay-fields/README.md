# OpenCode JS replay: reuse the fixed six-field list

Share the exact ordered list of allowed native replay fields across history blocks. Do not change type checks, omission of undefined values, restoration order, override rules or replay metadata.

Seventeen paired local controls matched on the owner and scoped sources. Two conversions in the same test module each used the same synthetic history with 6,144 recorded replay blocks, created by the local response collector. A narrow iterator probe observed 12,288 separate six-field list objects before and one shared object after. The number of field visits and the resulting request stayed the same.

These are logical object identities under instrumentation, not measured V8 allocation, RAM or time. No actual provider, SDK or application ran. The patch is for the optional JS model adapter, not the native Go provider.
