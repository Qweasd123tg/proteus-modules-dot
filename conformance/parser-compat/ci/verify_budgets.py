#!/usr/bin/env python3
"""Exact same-typed-input budget controls, separate from semantic observations."""
from verify_observations import expect, validate_outcome

KINDS = {
    "depth": ("quoted_metadata_scalar", "max_depth", 1, 4, "Depth", "max_depth"),
    "nodes": ("plain_valid", "max_nodes", 1, 256, "Nodes", "nodes"),
    "events": ("plain_valid", "max_events", 1, 256, "Events", "events"),
    "scalar_bytes": ("unicode_scalar", "max_total_scalar_bytes", 1, 65536, "ScalarBytes", "total_scalar_bytes"),
    "aliases": ("alias_string", "max_aliases", 0, 8, "Aliases", "aliases"),
    "comments": ("raw_bytes_16384", "max_total_comment_bytes", 1, 65536, "CommentBytes", "total_comment_bytes"),
    "reader_bytes": ("plain_valid", "max_reader_input_bytes", 1, 65536, "ReaderInputBytes", None),
}


def verify(corpus, semantic_rows, rows):
    cases = {case["id"]: case for case in corpus["cases"]}
    semantics = {(row["parser"], row["case_id"]): row for row in semantic_rows}
    required = {(kind, mode) for kind in KINDS for mode in ("permissive", "restrictive")}
    required.add(("comments", "comments_disabled"))
    indexed = {}
    for row in rows:
        expect(type(row) is dict and type(row.get("schema_version")) is int
               and row["schema_version"] == 1 and row.get("parser") == "serde_saphyr_budget",
               "invalid budget report version/parser")
        key = (row.get("kind"), row.get("mode"))
        expect(key in required and key not in indexed, "unknown or duplicate budget observation")
        kind, mode = key
        case_id, field, low, high, error_kind, counter = KINDS[kind]
        case = cases[case_id]
        expect(row.get("case_id") == case_id and row.get("yaml_sha256") == case["yaml_sha256"],
               "budget pair input identity changed")
        expect(type(row.get("raw_yaml_bytes")) is int
               and row["raw_yaml_bytes"] == case["yaml_utf8_bytes"], "budget raw bytes changed")
        expected_entry = ("typed Frontmatter from_reader_with_options over authored in-memory Cursor"
                          if kind == "reader_bytes" else "typed Frontmatter from_str_with_options")
        expect(row.get("entrypoint") == expected_entry, "budget entry point changed")
        limit = high if mode == "permissive" else low
        expect(row.get("limit_field") == field and type(row.get("limit")) is int
               and row["limit"] == limit and row.get("expected_restrictive_kind") == error_kind,
               "budget limit/profile drift")
        options = row.get("options_profile", {})
        expect(options.get("base") == "Options::default; one budget field overridden"
               and type(options.get("configured_debug")) is str
               and options.get("emit_comments") is (mode != "comments_disabled")
               and options.get("features") == ["deserialize", "comments"]
               and options.get("include_or_property_resolver_installed") is False,
               "budget options or enabled features changed")
        validate_outcome(row.get("outcome"), None)
        status = row["outcome"]["status"]
        reports = row.get("budget_reports")
        expect(type(reports) is list and len(reports) <= 1, "budget callback duplicated/malformed")
        for report in reports:
            expect(type(report) is dict, "invalid budget callback report")
            for name in ("events", "aliases", "anchors", "documents", "nodes", "max_depth",
                         "total_scalar_bytes", "total_comment_bytes", "recorded_anchor_events", "recorded_anchor_bytes"):
                expect(type(report.get(name)) is int and report[name] >= 0, "invalid budget counter")
        if mode == "restrictive":
            expect(status == "rejected" and row.get("typed_error_classification") == error_kind,
                   "restrictive control did not hit intended typed budget error")
            if counter is not None:
                expect(len(reports) == 1 and reports[0].get("breached") == error_kind
                       and reports[0][counter] > limit, "intended budget counter did not exceed limit")
            # Reader-byte errors are a separately typed IOError path; callback
            # availability does not substitute for FileTooLarge classification.
        else:
            expect(status == "accepted" and row.get("typed_error_classification") is None,
                   "permissive/disabled-comment positive control failed")
            control = semantics[("serde_saphyr", case_id)]["outcome"]
            expect(control["status"] == "accepted" and row["outcome"]["fields"] == control["fields"],
                   "same valid typed input did not preserve fields")
            expect(len(reports) == 1 and reports[0].get("breached") is None,
                   "successful parse lacks its budget callback")
            if counter is not None:
                expect(reports[0][counter] <= limit, "successful budget counter exceeds selected limit")
            if mode == "comments_disabled":
                expect(reports[0]["total_comment_bytes"] == 0, "disabled comment retention still counted")
        indexed[key] = row
    expect(set(indexed) == required, "exact 15 budget observations not present")
    return {"budget_controls": "passed", "same_input_pairs": 7,
            "comment_emission_non_guarantee_controls": 1,
            "reader_limit_scope": "reader API only; no from_str claim",
            "unsupported_configurable_controls": [
                {"parser": parser, "controls": sorted(KINDS),
                 "status": "not_exposed_or_tested_by_this_adapter",
                 "note": "public surface inspected; fixed internal recursion/alias checks remain; not a no-resource-limits claim"}
                for parser in ("baseline_typed", "yaml_serde")],
            "migration_acceptance": "not_granted"}
