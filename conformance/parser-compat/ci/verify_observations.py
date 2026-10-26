#!/usr/bin/env python3
"""Typed semantic observations, deliberately not a migration-acceptance gate."""
import json
import math

PARSERS = ("baseline_typed", "baseline_module", "yaml_serde", "serde_saphyr")
BODY = "Authored parser comparison body."


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def decode(text):
    def nonfinite(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"nonfinite JSON number: {value}")
        return parsed
    return json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite, parse_float=finite_float)


def expect(condition, message):
    if not condition:
        raise ValueError(message)


def validate_fields(fields):
    expect(type(fields) is dict, "accepted fields must be object")
    expect(set(fields) == {"name", "description", "license", "compatibility", "metadata",
                           "allowed-tools", "disable-model-invocation", "user-invocable"},
           "wrong frozen Frontmatter field set")
    expect(type(fields["name"]) is str and type(fields["description"]) is str,
           "required fields are not strings")
    for name in ("license", "compatibility", "allowed-tools"):
        expect(fields[name] is None or type(fields[name]) is str, "optional string type changed")
    expect(type(fields["disable-model-invocation"]) is bool, "hint bool type changed")
    expect(fields["user-invocable"] is None or type(fields["user-invocable"]) is bool,
           "optional hint bool type changed")
    metadata = fields["metadata"]
    expect(type(metadata) is dict and len(metadata) <= 64
           and all(type(k) is str and type(v) is str for k, v in metadata.items()),
           "typed metadata shape or visitor limit changed")


def validate_outcome(outcome, body):
    expect(type(outcome) is dict, "missing outcome")
    if outcome.get("status") == "accepted":
        validate_fields(outcome.get("fields"))
        measured = outcome.get("serialized_fields_bytes")
        expect(type(measured) is int, "serialized field byte count must be integer")
        # Corpus values use ordinary JSON escapes; this cross-check does not replace
        # the required actual Rust byte-length observation for expanded boundaries.
        encoded = json.dumps(outcome["fields"], ensure_ascii=False, separators=(",", ":")).encode()
        expect(measured == len(encoded), "reported Rust field-byte length inconsistent")
        expect(outcome.get("body") == body, "body/fence behavior differs")
    elif outcome.get("status") == "rejected":
        expect(type(outcome.get("display")) is str and bool(outcome["display"])
               and type(outcome.get("debug")) is str, "missing real rejection diagnostic")
        expect(outcome.get("classification") == "not_normalized", "rejection silently normalized")
    else:
        raise ValueError("unknown outcome status")


def check_status(observations, parser, case, status, fragments=()):
    outcome = observations[(parser, case)]["outcome"]
    expect(outcome["status"] == status, f"baseline control changed: {parser}/{case}")
    if status == "rejected":
        expect(all(fragment in outcome["display"] for fragment in fragments),
               f"wrong intended baseline error: {parser}/{case}")
    return outcome


def verify(corpus, envelopes, rows):
    cases = {case["id"]: case for case in corpus["cases"]}
    envelope_cases = {case["id"]: case for case in envelopes["cases"]}
    expect(len(cases) == len(corpus["cases"]) == 38, "corpus count/identity drift")
    expect(len(envelope_cases) == len(envelopes["cases"]) == 7, "envelope count/identity drift")
    required = {(parser, case) for parser in PARSERS for case in cases}
    required.update(("baseline_envelope", case) for case in envelope_cases)
    observations = {}
    for row in rows:
        expect(type(row) is dict and type(row.get("schema_version")) is int
               and row["schema_version"] == 1, "invalid observation version")
        key = (row.get("parser"), row.get("case_id"))
        expect(key in required and key not in observations, "unknown or duplicate observation")
        parser, case_id = key
        if parser == "baseline_envelope":
            case = envelope_cases[case_id]
            expect(row.get("entrypoint") == "frozen document::parse envelope control", "envelope entry point changed")
            expect(row.get("document_sha256") == case["document_sha256"], "envelope hash drift")
            expect(type(row.get("raw_document_bytes")) is int
                   and row["raw_document_bytes"] == case["document_utf8_bytes"], "envelope byte drift")
            expected = case["expected"]
            validate_outcome(row.get("outcome"), expected.get("body"))
            expect(row["outcome"]["status"] == expected["status"], "envelope status changed")
            if expected["status"] == "rejected":
                expect(expected["error_contains"] in row["outcome"]["display"], "wrong envelope error")
        else:
            case = cases[case_id]
            expect(row.get("entrypoint") == ("frozen module parse" if parser == "baseline_module"
                                             else "direct typed Frontmatter from_str"), "semantic entry point changed")
            expect(row.get("yaml_sha256") == case["yaml_sha256"], "case hash drift")
            expect(type(row.get("raw_yaml_bytes")) is int
                   and row["raw_yaml_bytes"] == case["yaml_utf8_bytes"], "case byte drift")
            validate_outcome(row.get("outcome"), BODY if parser == "baseline_module" else None)
            options = row.get("options_profile", {})
            if parser == "serde_saphyr":
                expect(options.get("selection") == "Options::default via from_str"
                       and type(options.get("debug")) is str and bool(options["debug"])
                       and options.get("features") == ["deserialize", "comments"]
                       and options.get("include_or_property_resolver_installed") is False,
                       "candidate default options/features changed")
            else:
                expect(options.get("selection") == "library default; no configurable budget API selected",
                       "baseline or yaml_serde option selection changed")
        observations[key] = row
    expect(set(observations) == required, "exact 159 observations not present")

    plain = check_status(observations, "baseline_typed", "plain_valid", "accepted")["fields"]
    expect(plain["name"] == "review" and plain["description"] == "Typed parser comparison",
           "baseline positive does not parse intended fields")
    for parser in PARSERS:
        observed = check_status(observations, parser, "plain_valid", "accepted")
        expect(observed["fields"] == plain, "candidate positive control changed fields")
    for case, fragments in {
        "identical_known_duplicate": ("duplicate field", "name"),
        "identical_metadata_duplicate": ("duplicate metadata key",),
        "metadata_keys_65": ("at most 64 metadata keys",),
        "unknown_top_level": ("unknown field", "unrecognized-field"),
    }.items():
        for parser in ("baseline_typed", "baseline_module"):
            check_status(observations, parser, case, "rejected", fragments)
    for count in (16383, 16384, 16385):
        case = f"expanded_json_bytes_{count}"
        actual = check_status(observations, "baseline_typed", case, "accepted")
        expect(actual["serialized_fields_bytes"] == cases[case]["predicted_serialized_fields_bytes"] == count,
               "Rust expanded size differs from corpus prediction")
        check_status(observations, "baseline_module", case,
                     "accepted" if count <= 16384 else "rejected",
                     () if count <= 16384 else ("expanded frontmatter exceeds 16384 serialized bytes",))
        check_status(observations, "baseline_typed", f"raw_bytes_{count}", "accepted")
        check_status(observations, "baseline_module", f"raw_bytes_{count}",
                     "accepted" if count <= 16384 else "rejected",
                     () if count <= 16384 else ("frontmatter exceeds 16384 bytes",))
    for prefix, limit, diagnostic in (
        ("description_chars", 1024, "description must be nonblank and <=1024 characters"),
        ("compatibility_chars", 500, "compatibility must be nonblank and <=500 characters"),
    ):
        for count in (limit, limit + 1):
            check_status(observations, "baseline_typed", f"{prefix}_{count}", "accepted")
            check_status(observations, "baseline_module", f"{prefix}_{count}",
                         "accepted" if count == limit else "rejected",
                         () if count == limit else (diagnostic,))
    check_status(observations, "baseline_module", "metadata_keys_64", "accepted")
    expanded = check_status(observations, "baseline_typed", "expanded_metadata_limit", "accepted")
    expect(expanded["serialized_fields_bytes"] > 16384, "alias case did not reach expanded bound")
    check_status(observations, "baseline_module", "expanded_metadata_limit", "rejected",
                 ("expanded frontmatter exceeds 16384 serialized bytes",))

    comparisons = []
    for parser in ("yaml_serde", "serde_saphyr"):
        for case in cases:
            old = observations[("baseline_typed", case)]["outcome"]
            new = observations[(parser, case)]["outcome"]
            if old["status"] != new["status"]:
                relation = "acceptance_difference"
            elif old["status"] == "rejected":
                relation = "both_rejected_not_proven_equivalent"
            elif old["fields"] == new["fields"]:
                relation = "same_typed_fields"
            else:
                relation = "typed_field_difference"
            comparisons.append({"parser": parser, "case_id": case, "relation": relation})
    return {"observation_integrity": "passed", "observation_count": 159,
            "comparisons": comparisons, "migration_acceptance": "not_granted",
            "budget_coverage": "separate required gate; not established here"}
