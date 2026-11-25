# Pi turn setup: build history in its final layout

Build the Pi loop's initial state and separate tail directly from canonical history. Start the state with the synthesized system message and project the remaining messages in order with the same shared tool-name map. This avoids shifting every earlier projected message one slot to make room for the system message.

This is turn setup in the Pi profile, not Desktop startup or history reopening. The patch does not change the later token estimate, history checkpoints, model requests, or authorization. See the receipt for source identities, verification, and limits.
