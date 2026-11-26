# Move Anthropic argument fragments into stream events

Move the decoded nonempty `partial_json` string into `ToolCallDelta`.
Still append exact bytes to the block's accumulator, still replace the
initial input on a nonempty fragment, and preserve terminal validation.
Missing, nonstring, empty, and unmatched fragments remain no-ops.

Exact Modules base: `6b290ebff828427ab66ef9c4ff3b24cef3627603`. For the exact after-#845 tree
use the alternative in `receipt.json`, not both. Strict indexed
apply/reverse verified. Four optimized unmasked model-pack libraries
built, with 32 focused native tests passing per arm.

In synthetic translation of a 96 KiB fragment, allocation requests went
from 12 to 11, removing 98304 requested bytes. Escaped
Unicode and final canonical arguments matched. No provider or tools
were called.
