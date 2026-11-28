# Desktop extension framing: use the frame budget and closure flag directly

Desktop extension I/O no longer depends on the entire child-process state. Its reader receives references to the same incoming byte budget and closed flag. The process still owns lifecycle, parsing, and delivery. The permit remains attached to the delivered message.

No wire format, limits, newline or final EOF behavior, charging, or closing policy changed. SDK and native Codex framing remain separate. The patch is for Proteus-harness/Proteus-desktop at `4015530444740e56fe35f8dfa27b4571cdd2ffcc`. It also applies over the checked cumulative Desktop stack. See `receipt.json` for source and native verification.
