// Authored opt-in example, not an SDK patch, lossless parser or authority gate.
// Cooperating same-realm ordinary data only; no proxies or modified intrinsics.
export const LIMITS = Object.freeze({ depth: 32, nodes: 4096, textUnits: 65536 });

function refuse(code) {
  const error = new Error(`argument replacement refused: ${code}`);
  error.name = "ArgumentReplacementError";
  error.code = code;
  // Never set error.data: the selected host treats RPC data as ModelFailure.
  throw error;
}

function inspectTree(root) {
  const pending = [{ value: root, depth: 0 }];
  const seen = new WeakSet();
  let visited = 0;
  let textUnits = 0;
  const text = (length) => {
    textUnits += length;
    if (textUnits > LIMITS.textUnits) refuse("budget_text");
  };
  const childrenFit = (count, depth) => {
    // Refuse before allocating a child worklist. Own-key reflection above this
    // check can already allocate: this is not an RSS or parsing limit.
    if (visited + pending.length + count > LIMITS.nodes) refuse("budget_nodes");
    if (count > 0 && depth >= LIMITS.depth) refuse("budget_depth");
  };
  while (pending.length > 0) {
    const { value, depth } = pending.pop();
    visited += 1;
    if (visited > LIMITS.nodes) refuse("budget_nodes");
    if (depth > LIMITS.depth) refuse("budget_depth");
    if (value === null || typeof value === "boolean") continue;
    if (typeof value === "string") { text(value.length); continue; }
    if (typeof value === "number") {
      if (!Number.isFinite(value)) refuse("non_finite");
      if (Number.isInteger(value) && !Number.isSafeInteger(value)) refuse("unsafe_integer");
      continue;
    }
    if (typeof value !== "object") refuse("unsupported_value");
    const array = Array.isArray(value);
    const prototype = Object.getPrototypeOf(value);
    if (array ? prototype !== Array.prototype :
        prototype !== Object.prototype && prototype !== null) refuse("unsupported_shape");
    if (seen.has(value)) refuse("repeated_reference");
    seen.add(value);
    const keys = Reflect.ownKeys(value);
    if (array) {
      const length = Object.getOwnPropertyDescriptor(value, "length").value;
      if (keys.length !== length + 1 || keys[keys.length - 1] !== "length") {
        refuse("unsupported_shape");
      }
      childrenFit(length, depth);
      for (let index = 0; index < length; index += 1) {
        if (keys[index] !== String(index)) refuse("unsupported_shape");
        const entry = Object.getOwnPropertyDescriptor(value, keys[index]);
        if (!entry.enumerable || !("value" in entry)) refuse("unsupported_shape");
        pending.push({ value: entry.value, depth: depth + 1 });
      }
    } else {
      childrenFit(keys.length, depth);
      for (const key of keys) {
        if (typeof key !== "string") refuse("unsupported_shape");
        const entry = Object.getOwnPropertyDescriptor(value, key);
        if (!entry.enumerable || !("value" in entry)) refuse("unsupported_shape");
        text(key.length);
        pending.push({ value: entry.value, depth: depth + 1 });
      }
    }
  }
}

/**
 * Inspect only an outbound tool_arguments candidate, at this instant.
 * No cloning, freezing, normalization or recovery of original JSON tokens.
 * Callers must not mutate the candidate after this returns. Safe results from
 * earlier rounded computations still pass; each replacing handler must opt in.
 */
export function guardArgumentReplacement(response) {
  if (response === null || typeof response !== "object") return response;
  const action = Object.getOwnPropertyDescriptor(response, "action");
  if (!action) return response; // Existing SDK owns invalid-response validation.
  if (!("value" in action)) refuse("outer_accessor");
  if (action.value !== "tool_arguments") return response;
  const prototype = Object.getPrototypeOf(response);
  if (prototype !== Object.prototype && prototype !== null) refuse("unsupported_shape");
  const args = Object.getOwnPropertyDescriptor(response, "args");
  if (!args) refuse("missing_args");
  if (!("value" in args)) refuse("outer_accessor");
  inspectTree(args.value);
  return response;
}
