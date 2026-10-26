// Authored integration proposal only. No commands, host callbacks or network.
import { guardArgumentReplacement } from "./guard.mjs";

export default function setup(hooks) {
  const mode = hooks.config.mode;
  if (!["continue", "guarded", "computed_safe", "unguarded_later"].includes(mode)) {
    throw new Error("unsupported guard fixture mode");
  }
  hooks.on("before_tool", ({ call }) => {
    if (mode === "continue") return guardArgumentReplacement(undefined);
    const args = mode === "computed_safe" ? { value: call.args.value - 9007199254740992 } :
      mode === "unguarded_later" ? { value: 0 } : call.args;
    return guardArgumentReplacement({ action: "tool_arguments", args });
  });
  if (mode === "unguarded_later") {
    // Intentional limit control: guarding one producer is not global middleware.
    hooks.on("before_tool", () => ({ action: "tool_arguments", args: { value: 9007199254740992 } }));
  }
}
