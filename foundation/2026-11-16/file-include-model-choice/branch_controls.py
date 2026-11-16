#!/usr/bin/env python3
"""Authored branch algebra and real JSON/TOML parser controls; not Rust execution.

The only modeled behavior is the choice-key branch in the two source writers,
recursive object merge, and the loader's mutually-exclusive-key predicate.
AppConfig, Save, async publication, provider workers and tests are NOT executed.
"""
import copy
import json
import tomllib


def choice_write(document, selected, baseline, inline=False):
    """Minimal shared decision from persistence.rs, no preset-map modifications."""
    choice_changed = selected != baseline
    presets_changed = False
    named = 'models' in document or 'model' in document
    had_providers = 'providers' in document
    has_choice = 'model' in document or 'active_provider' in document
    if named or (not has_choice and not had_providers and (choice_changed or presets_changed)):
        document.pop('active_provider', None)
        document.pop('providers', None)
        if has_choice or choice_changed or not inline:
            document['model'] = selected
    elif has_choice or choice_changed or not inline:
        document['active_provider'] = selected
    return document


def merge(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        for key, value in b.items():
            a[key] = merge(a.get(key), copy.deepcopy(value))
        return a
    return copy.deepcopy(b)


def fixture(named, format):
    choice, catalog = ('model', 'models') if named else ('active_provider', 'providers')
    if format == 'toml':
        base = tomllib.loads(f'{choice} = "main"\n[{catalog}.main]\nprovider = "fake"\nmodel = "large"\n[{catalog}.budget]\nprovider = "fake"\nmodel = "small"\n')
        wrapper = tomllib.loads('include = "base.toml"\n')
    else:
        base = json.loads(json.dumps({choice: 'main', catalog: {
            'main': {'provider': 'fake', 'model': 'large'},
            'budget': {'provider': 'fake', 'model': 'small'}}}))
        wrapper = json.loads('{"include": "base.json"}')
    return base, wrapper


def run():
    outcomes = []
    for format in ['toml', 'json']:
        for named in [False, True]:
            for switch in [False, True]:
                base, wrapper = fixture(named, format)
                before = copy.deepcopy(base)
                selected = 'budget' if switch else 'main'
                saved = choice_write(wrapper, selected, 'main')
                merged = merge(copy.deepcopy(base), saved)
                rejected = 'model' in merged and 'active_provider' in merged
                expected = named != switch
                assert rejected == expected
                assert base == before
                assert 'models' not in saved and 'providers' not in saved
                outcomes.append({'format': format, 'source': 'named' if named else 'provider',
                                 'edit': 'switch' if switch else 'unrelated',
                                 'writer_choice_keys': [key for key in ['model', 'active_provider'] if key in saved],
                                 'merged_choice_keys': [key for key in ['model', 'active_provider'] if key in merged],
                                 'source_predicate_would_reject': rejected})
    return {'kind': 'authored branch controls, NOT Rust runtime',
            'outcomes': outcomes, 'expected_rejections': sum(x['source_predicate_would_reject'] for x in outcomes),
            'expected_acceptances': sum(not x['source_predicate_would_reject'] for x in outcomes)}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
