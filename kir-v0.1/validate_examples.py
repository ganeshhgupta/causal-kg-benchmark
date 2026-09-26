#!/usr/bin/env python3
"""Validate every hand-compiled example against kir-schema.json, atom by atom.
Reports pass/fail per atom rather than stopping at the first error, since the
point of this exercise is to find every break, not just the first one."""
import json
import sys
from pathlib import Path

import jsonschema

root = Path(__file__).parent
schema = json.load(open(root / "kir-schema.json", encoding="utf-8"))
examples = json.load(open(root / "examples.json", encoding="utf-8"))["atoms"]

validator = jsonschema.Draft202012Validator(schema)

failures = 0
for atom in examples:
    errors = sorted(validator.iter_errors(atom), key=lambda e: e.path)
    if errors:
        failures += 1
        print(f"FAIL {atom['id']}:")
        for e in errors:
            path = "/".join(str(p) for p in e.path)
            print(f"   at '{path}': {e.message}")
    else:
        print(f"PASS {atom['id']}")

print(f"\n{len(examples) - failures}/{len(examples)} atoms validate cleanly against kir-schema.json (syntactic/structural validity only -- says nothing about whether the atom faithfully represents its surface_forms, which is the deeper problem documented in STRESS_TEST.md).")
sys.exit(1 if failures else 0)
