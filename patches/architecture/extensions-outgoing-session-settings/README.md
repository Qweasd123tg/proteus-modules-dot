# Extensions SDK: keep outgoing admission out of the incoming queue

`Host::set_session` and its existing pending-request budget now live together in a private SDK module. The incoming queue no longer owns policy for an outgoing command. The public method, feature/session checks, request and byte limits, JSON envelope, and acknowledgement routing are unchanged.

Use `source.patch` on Proteus-harness/Proteus-desktop-extensions at `d12bedf7f4518f8b54127c8c6bdbcfc1c923cd8d`. No earlier accepted architecture patch changed this Extensions source tree. The same six selected in-memory SDK tests ran before and after the change. See `receipt.json`.
