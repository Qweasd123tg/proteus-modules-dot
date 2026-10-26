"""Synthetic verifier inputs only. No YAML is parsed and no parser result is claimed."""
import copy
import json
from pathlib import Path

from verify_observations import PARSERS, BODY
from verify_budgets import KINDS

PACKAGE = Path(__file__).resolve().parent.parent


def fixtures():
    corpus = json.loads((PACKAGE / "fixtures/corpus.json").read_text())
    envelopes = json.loads((PACKAGE / "fixtures/envelopes.json").read_text())
    return corpus, envelopes


def plain_fields():
    return {"name": "review", "description": "Typed parser comparison", "license": None,
            "compatibility": None, "metadata": {}, "allowed-tools": None,
            "disable-model-invocation": False, "user-invocable": None}


def accept(fields, body=None):
    return {"status": "accepted", "fields": fields, "body": body,
            "serialized_fields_bytes": len(json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode())}


def reject(message):
    return {"status": "rejected", "display": message, "debug": "synthetic: " + message,
            "classification": "not_normalized"}


def rows():
    corpus, envelopes = fixtures()
    result = []
    errors = {"identical_known_duplicate": "duplicate field `name`",
              "identical_metadata_duplicate": "duplicate metadata key",
              "metadata_keys_65": "at most 64 metadata keys",
              "unknown_top_level": "unknown field `unrecognized-field`"}
    for parser in PARSERS:
        for case in corpus["cases"]:
            name = case["id"]
            fields = plain_fields()
            if name.startswith("description_chars_"):
                fields["description"] = "я" * int(name.rsplit("_", 1)[1])
            if name.startswith("compatibility_chars_"):
                fields["compatibility"] = "я" * int(name.rsplit("_", 1)[1])
            if name.startswith("expanded_json_bytes_"):
                target = int(name.rsplit("_", 1)[1])
                fields["license"] = ""
                base_size = accept(fields)["serialized_fields_bytes"]
                fields["license"] = "x" * (target - base_size)
            if name == "expanded_metadata_limit":
                fields["license"] = "x" * 300
                fields["metadata"] = {f"key-{i}": "x" * 300 for i in range(60)}
            if name == "metadata_keys_64":
                fields["metadata"] = {f"key-{i}": "value" for i in range(64)}
            outcome = accept(fields, BODY if parser == "baseline_module" else None)
            if parser in ("baseline_typed", "baseline_module") and name in errors:
                outcome = reject(errors[name])
            if parser == "baseline_module":
                if name in ("expanded_json_bytes_16385", "expanded_metadata_limit"):
                    outcome = reject("expanded frontmatter exceeds 16384 serialized bytes")
                elif name == "raw_bytes_16385":
                    outcome = reject("frontmatter exceeds 16384 bytes")
                elif name == "description_chars_1025":
                    outcome = reject("description must be nonblank and <=1024 characters")
                elif name == "compatibility_chars_501":
                    outcome = reject("compatibility must be nonblank and <=500 characters")
            options = ({"selection": "Options::default via from_str", "debug": "synthetic defaults",
                        "features": ["deserialize", "comments"], "include_or_property_resolver_installed": False}
                       if parser == "serde_saphyr" else {"selection": "library default; no configurable budget API selected"})
            result.append({"schema_version": 1, "parser": parser, "case_id": name,
                           "entrypoint": "frozen module parse" if parser == "baseline_module" else "direct typed Frontmatter from_str",
                           "yaml_sha256": case["yaml_sha256"], "raw_yaml_bytes": case["yaml_utf8_bytes"],
                           "outcome": outcome, "options_profile": options})
    for case in envelopes["cases"]:
        expected = case["expected"]
        result.append({"schema_version": 1, "parser": "baseline_envelope", "case_id": case["id"],
                       "entrypoint": "frozen document::parse envelope control",
                       "document_sha256": case["document_sha256"], "raw_document_bytes": case["document_utf8_bytes"],
                       "outcome": accept(plain_fields(), expected["body"]) if expected["status"] == "accepted"
                       else reject(expected["error_contains"])})
    return result


def budgets(semantic_rows):
    corpus, _ = fixtures()
    cases = {case["id"]: case for case in corpus["cases"]}
    semantic = {(row["parser"], row["case_id"]): row for row in semantic_rows}
    result = []
    for kind, (case_id, field, low, high, category, counter) in KINDS.items():
        for mode in ("permissive", "restrictive", "comments_disabled") if kind == "comments" else ("permissive", "restrictive"):
            case = cases[case_id]
            limit = high if mode == "permissive" else low
            report = {"breached": None, "events": 16, "aliases": 1, "anchors": 1,
                      "documents": 1, "nodes": 8, "max_depth": 2, "total_scalar_bytes": 60,
                      "total_comment_bytes": 100, "recorded_anchor_events": 1, "recorded_anchor_bytes": 0}
            outcome = copy.deepcopy(semantic[("serde_saphyr", case_id)]["outcome"])
            classified = None
            if mode == "restrictive":
                outcome = reject("synthetic intended budget error")
                classified = category
                if counter:
                    report["breached"] = category
                    report[counter] = limit + 1
            elif mode == "comments_disabled":
                report["total_comment_bytes"] = 0
            result.append({"schema_version": 1, "parser": "serde_saphyr_budget", "kind": kind, "mode": mode,
                           "case_id": case_id, "yaml_sha256": case["yaml_sha256"], "raw_yaml_bytes": case["yaml_utf8_bytes"],
                           "entrypoint": "typed Frontmatter from_reader_with_options over authored in-memory Cursor"
                           if kind == "reader_bytes" else "typed Frontmatter from_str_with_options",
                           "limit_field": field, "limit": limit, "expected_restrictive_kind": category,
                           "options_profile": {"base": "Options::default; one budget field overridden", "configured_debug": "synthetic options",
                                               "emit_comments": mode != "comments_disabled", "features": ["deserialize", "comments"],
                                               "include_or_property_resolver_installed": False},
                           "outcome": outcome, "typed_error_classification": classified, "budget_reports": [report]})
    return result
