# Optional Python workflow: assemble the final response text once

The opt-in agent-worker used to join response fragments to choose the latest assistant message with visible text, then join the chosen message again. Select using the same whitespace rule and assemble the selected text once. Preserve the original whitespace and fragment order, and keep the newest message as the fallback when every message is blank.

There is no change to the response validator, model or tool path, canonical history, or checkpoint: the worker still adopts the host's checkpoint before emitting TurnFinished. This affects the optional Python workflow, not the default Desktop workflow. See the receipt for isolated standard-library tests and their limits.
