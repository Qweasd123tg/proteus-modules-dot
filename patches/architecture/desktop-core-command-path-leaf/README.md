# Desktop: share selection of the Core command without coupling to its process

Catalog inventory and provider auth now obtain the Core command from a private runtime-path module rather than importing the process supervisor. The selector keeps explicit OS-string overrides and aliases raw, then falls back to a sibling file or the bare command as before. Only inventory resolves a canonical path for metadata inspection; launch and provider auth keep using the raw command's parent according to their existing rules.

No changes to provider admission, execution or secret handling, Core lifecycle, extension or module packages, or wire contracts. Apply to exact Desktop `4015530444740e56fe35f8dfa27b4571cdd2ffcc` or to the cumulative Desktop architecture stack. Native fixtures verify raw selection and inventory behavior without running Core or auth processes.
