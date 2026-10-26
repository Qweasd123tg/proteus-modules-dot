"""Bounded gate's exact JSON subset, not a replacement SDK parser."""
import json


def unique_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def reject_number(_token):
    raise ValueError("non-integer or non-finite JSON number")


def loads(text):
    return json.loads(text, object_pairs_hook=unique_object, parse_int=int,
                      parse_float=reject_number, parse_constant=reject_number)
