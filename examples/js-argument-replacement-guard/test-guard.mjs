// Authored pure controls. Not executed at source freeze; no SDK/Core imports.
import assert from "node:assert/strict";
import { guardArgumentReplacement as guard, LIMITS } from "./guard.mjs";

const tests = [];
const test = (name, fn) => {
  assert(!tests.some(([prior]) => prior === name), "duplicate test name");
  tests.push([name, fn]);
};
const candidate = (args) => ({ action: "tool_arguments", args });
const accepted = (args) => {
  const response = candidate(args);
  assert.strictEqual(guard(response), response);
  assert.strictEqual(response.args, args);
  return response;
};
const fails = (fn, code) => {
  let error;
  try { fn(); } catch (caught) { error = caught; }
  assert(error instanceof Error, `expected refusal ${code}`);
  assert.equal(error.name, "ArgumentReplacementError");
  assert.equal(error.code, code);
  assert.equal(error.message, `argument replacement refused: ${code}`);
  assert(!("data" in error), "must not masquerade as ModelFailure data");
  return error;
};
const refused = (args, code) => fails(() => guard(candidate(args)), code);
const chain = (depth) => {
  let value = 0;
  for (let i = 0; i < depth; i += 1) value = [value];
  return value;
};

test("continue_undefined", () => assert.equal(guard(undefined), undefined));
test("continue_identity_no_args_read", () => {
  const ordinary = Object.freeze({ action: "continue" });
  assert.strictEqual(guard(ordinary), ordinary);
  let reads = 0;
  const response = { action: "continue", get args() { reads += 1; return 9007199254740992; } };
  assert.strictEqual(guard(response), response);
  assert.equal(reads, 0); // Invalid extra field stays the SDK's responsibility.
});
test("nonreplacement_untouched", () => {
  for (const action of ["block_tool", "tool_output", "unknown"]) {
    const response = { action, args: 9007199254740992 };
    assert.strictEqual(guard(response), response);
  }
});
test("invalid_response_left_to_sdk", () => {
  for (const response of [null, false, 1, "continue", {}, []]) {
    assert.strictEqual(guard(response), response);
  }
});
test("outer_action_accessor_not_called", () => {
  let reads = 0;
  fails(() => guard({ get action() { reads += 1; return "tool_arguments"; }, args: 1 }), "outer_accessor");
  assert.equal(reads, 0);
});
test("outer_args_accessor_not_called", () => {
  let reads = 0;
  fails(() => guard({ action: "tool_arguments", get args() { reads += 1; return 1; } }), "outer_accessor");
  assert.equal(reads, 0);
});
test("missing_replacement_args", () => fails(() => guard({ action: "tool_arguments" }), "missing_args"));
test("safe_integer_boundaries", () => accepted({ plus: 9007199254740991, minus: -9007199254740991, zero: 0 }));
test("nested_null_prototype_and_frozen_data", () => {
  const object = Object.assign(Object.create(null), { value: 7 });
  Object.freeze(object);
  accepted(Object.freeze({ a: Object.freeze([object, null, true, "x"]) }));
});
test("unsafe_exact_boundaries_conservatively_refused", () => {
  for (const value of [9007199254740992, -9007199254740992]) refused({ value }, "unsafe_integer");
});
test("unsafe_rounded_tokens_refused", () => {
  const positive = JSON.parse("9007199254740993");
  const negative = JSON.parse("-9007199254740993");
  assert.equal(positive, 9007199254740992);
  assert.equal(negative, -9007199254740992);
  refused({ value: positive }, "unsafe_integer");
  refused({ value: negative }, "unsafe_integer");
});
test("large_decimal_strings_unchanged", () => {
  const response = accepted({ plus: "9007199254740993", minus: "-9007199254740993" });
  assert.equal(response.args.plus, "9007199254740993");
  assert.equal(response.args.minus, "-9007199254740993");
});
test("finite_fraction_and_signed_zero_not_lexical_guarantee", () => {
  const response = accepted({ fraction: 0.125, zero: -0 });
  assert(Object.is(response.args.zero, -0));
});
test("nonfinite_values_refused", () => {
  for (const value of [NaN, Infinity, -Infinity]) refused({ value }, "non_finite");
});
test("computed_safe_value_from_rounded_input_is_not_detected", () => {
  const value = JSON.parse("9007199254740993") - 9007199254740992;
  assert.equal(value, 0);
  assert.equal(9007199254740993n - 9007199254740992n, 1n); // Test-only exact integer oracle.
  assert.equal(accepted({ value }).args.value, 0);
});
test("post_check_mutation_is_not_prevented", () => {
  const response = accepted({ value: 1 });
  response.args.value = 9007199254740992;
  assert.equal(response.args.value, 9007199254740992);
  fails(() => guard(response), "unsafe_integer"); // Only a new inspection refuses.
});
test("depth_exact_32", () => accepted(chain(32)));
test("depth_33_refused", () => refused(chain(33), "budget_depth"));
test("nodes_exact_4096_including_root", () => accepted(Array(4095).fill(0)));
test("nodes_4097_refused_before_child_descriptors", () => {
  let reads = 0;
  const value = Array(4096).fill(0);
  Object.defineProperty(value, "0", { enumerable: true, get() { reads += 1; return 0; } });
  refused(value, "budget_nodes");
  assert.equal(reads, 0);
});
test("text_exact_65536", () => accepted("x".repeat(65536)));
test("text_65537_refused", () => refused("x".repeat(65537), "budget_text"));
test("keys_and_values_share_text_budget", () => {
  accepted({ key: "x".repeat(65533) });
  refused({ key: "x".repeat(65534) }, "budget_text");
});
test("supplementary_characters_count_two_utf16_units", () => {
  accepted("😀".repeat(32768));
  refused("😀".repeat(32768) + "x", "budget_text");
});
test("array_index_names_do_not_consume_text_budget", () => accepted(["x".repeat(65536)]));
test("unsupported_scalar_types_refused", () => {
  for (const value of [undefined, 1n, Symbol("fixture"), () => 0]) refused({ value }, "unsupported_value");
});
test("object_accessor_refused_without_invocation", () => {
  let reads = 0;
  refused({ get value() { reads += 1; return 1; } }, "unsupported_shape");
  assert.equal(reads, 0);
});
test("array_accessor_refused_without_invocation", () => {
  let reads = 0;
  const array = [1];
  Object.defineProperty(array, "0", { enumerable: true, get() { reads += 1; return 1; } });
  refused(array, "unsupported_shape");
  assert.equal(reads, 0);
});
test("nonenumerable_properties_refused", () => {
  const value = {};
  Object.defineProperty(value, "hidden", { value: 1 });
  refused(value, "unsupported_shape");
});
test("symbol_keys_refused", () => refused({ [Symbol("fixture")]: 1 }, "unsupported_shape"));
test("array_holes_and_extra_properties_refused", () => {
  refused(Array(1), "unsupported_shape");
  refused(Object.assign([1], { extra: 2 }), "unsupported_shape");
  const disguisedHole = Array(1); disguisedHole.extra = 1;
  refused(disguisedHole, "unsupported_shape");
});
test("special_prototypes_refused", () => {
  for (const value of [new Date(0), new Map(), new Number(1), new Uint8Array(1), Object.create({})]) {
    refused(value, "unsupported_shape");
  }
  fails(() => guard(Object.assign(Object.create({}), candidate(1))), "unsupported_shape");
});
test("cycle_refused", () => {
  const value = {}; value.self = value;
  refused(value, "repeated_reference");
});
test("acyclic_shared_reference_conservatively_refused", () => {
  const shared = { value: 1 };
  refused([shared, shared], "repeated_reference");
});
test("distinct_equal_objects_accepted", () => accepted([{ value: 1 }, { value: 1 }]));
test("bounded_error_omits_values_keys_and_data", () => {
  const secret = "fixture-private-key";
  const error = refused({ [secret]: 9007199254740992 }, "unsafe_integer");
  assert(!error.message.includes(secret));
  assert(!error.message.includes("9007199254740992"));
  assert(error.message.length < 80);
  assert.deepEqual(Object.keys(error).sort(), ["code", "name"]);
});
test("fixed_limits_are_frozen", () => {
  assert.deepEqual(LIMITS, { depth: 32, nodes: 4096, textUnits: 65536 });
  assert(Object.isFrozen(LIMITS));
  assert.throws(() => { LIMITS.nodes = 1; }, TypeError);
});
test("refusal_does_not_mutate_original_candidate", () => {
  const response = Object.freeze(candidate(Object.freeze({ value: 9007199254740992 })));
  const before = JSON.stringify(response);
  fails(() => guard(response), "unsafe_integer");
  assert.equal(JSON.stringify(response), before);
});

const passed = [];
try {
  assert.equal(tests.length, 38, "frozen required control count");
  for (const [name, run] of tests) { run(); passed.push(name); }
  process.stdout.write(JSON.stringify({ schema_version: 1, status: "passed", controls: passed }) + "\n");
} catch (error) {
  process.stdout.write(JSON.stringify({ schema_version: 1, status: "failed", controls: passed,
    failed_control: tests[passed.length]?.[0] ?? "inventory", error: String(error.message).slice(0, 1000) }) + "\n");
  process.exitCode = 1;
}
