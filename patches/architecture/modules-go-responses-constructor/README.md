# Modules: Responses owns its OpenCode Go client constructor

OpenCode Go still owns model discovery, credentials, account usage and catalog state. The existing Responses client constructor now lives with Responses, removing the Go metadata module's reverse source dependency. The streaming and non-streaming clients still take the same shared state. Configuration validation, redirect policy, request fields, session affinity and package/protocol contracts are unchanged.

The same patch applies to exact Modules `7274147162cb226f05df13a52b4a271fa5619313` and the prior Modules architecture stack. The targeted library tests use local synthetic SQLite/JSON and scripted loopback HTTP. The streaming test parses a synthetic tool-call record; it does not invoke a tool, contact an external provider or run an agent. Production redirect policy is established by source comparison, not by the loopback fixture.
