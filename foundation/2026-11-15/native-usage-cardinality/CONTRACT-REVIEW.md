# Independent F4 usage-cardinality contract review

## Verdict

The proposed shared evidence helper is a coherent bounded robustness fix worth an exact candidate review. No need for a new framework or HOLD on the basic invariant. This remains known F4, not evidence that pinned Pi ordinarily omits required usage. No project execution/imports/tests performed in this review.

Read the Pi/Codex usage projection and sum_usage in the prior reviewed PR127 after tree, plus the historical F4 excerpt. Current filtering drops non-dict usage before sum_usage, so surviving complete rows can be promoted despite missing expected contributors. Existing strict per-field checking cannot recover the lost denominator.

## Proposed invariant

Expected rows means the observed completed assistant messages for Pi and observed turn.completed events for Codex. It is not Pi agent_settled count, Codex model request count, every attempted/active request, or universal billed-call coverage. Missing entire events cannot be detected by this denominator. Retain native_usage as the old observed dictionary list; evidence fields explain its completeness rather than silently changing raw-list meaning.

For each category, full provider_usage is numeric only when expected_rows is positive, len(observed rows)==expected_rows, and every expected contribution has type(value) is int. For composite mappings, each row contributes only when all component fields are exact integers. Category reported-row count records that criterion, not any one component being present. Count can be zero; absent total and absent partial remain None. Explicit known zero is numeric zero with positive coverage, not indistinguishable from no evidence.

partial_reported_usage_sums should sum available qualifying row contributions even when full cardinality is missing. For Pi combined input, compute input+cacheRead+cacheWrite within each fully known row before partial summation. Do not add separately observed component subtotals from disjoint coverage: that would invent whole-row evidence. Preserve each independently mapped component category, so this conservative composite projection does not erase raw/component observations.

With all valid expected rows present, ordinary integer totals are algebraically unchanged from the old Pi sum-of-complete-column-totals. Empty inputs stay unknown, matching old sum_usage. Bool remains excluded by exact-int checks. This policy does not reject negative integers or comprehensively validate malformed artifacts; calling sums lower bounds assumes legitimate nonnegative counters, as before. Do not extend this patch into a new normalization policy without a reason.

## Helper boundary and other consumers

One helper with explicit expected_rows and string-or-tuple field mapping is small and purposeful: it owns complete sums, observed sums and category coverage together. Adapter call sites choose their native cardinality. No lifecycle classifier change is needed; a clean completed task can still have unknown token totals. PR126 already consumes partial_reported_usage_sums, while PR127 terminal outcome remains independent.

A compatibility sum_usage(rows,mapping) wrapper delegating to evidence(rows,mapping,len(rows))['provider_usage'] is acceptable for the inspected list-of-dict/string-mapping callers. Its full totals match the old per-field exact-int rule, including empty and missing fields, so OpenCode value semantics can stay unchanged without a second summation implementation. It creates extra temporary evidence dictionaries; do not claim performance improvement or an independently corrected OpenCode cardinality contract. No blanket equivalence promise for arbitrary generators, malformed rows or undocumented mapping types.

## Exact candidate requirements

Test whole missing/null/non-dict usage among otherwise known Pi/Codex rows; missing individual categories; all missing/empty event sets; zero; bool versus int; complete valid totals; incomplete composite rows with disjoint component coverage; raw native_usage preservation; and the sum_usage compatibility wrapper. Keep lifecycle/pipeline/model counters unchanged. A category count plus expected denominator should remain inspectable when strict totals become None.

Report tests should demonstrate PR126 retaining partial evidence without promoting it to full totals even when lifecycle is complete. Historical scores/files must not be rewritten, and changed classification should be limited to newly evaluated incomplete artifacts. Proposed tests are not runtime evidence. Exact patch acceptance, type handling and preservation claims await actual code/diff review.
