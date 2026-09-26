# K-IR v0.1

The formal representation the project has been implicitly using in JSON all
along, made explicit — plus a deliberate attempt to break it before writing
any compiler.

## Files

```
kir-schema.json        Formal JSON Schema (2020-12) for a single K-IR
                        proposition atom: predicate + arguments + direction
                        + quantification + context + polarity + modality
                        + provenance + surface_forms.
examples.json           26 hand-compiled atoms: 14 from the physics/ML
                        benchmarks' known-hardest cases (Copper/Metal
                        specialization, water 0-4C, Dropout train/inference,
                        BatchNorm's two hypotheses, DropConnect/Dropout),
                        12 from a deliberately different cross-domain batch
                        (math, probability, algorithms, distributed
                        systems, networking, relativity) chosen to test
                        structurally different failure modes.
validate_examples.py    Validates every atom against kir-schema.json.
                        Result: 26/26 pass -- see STRESS_TEST.md finding 0
                        for why that's a finding, not a clean bill of health.
STRESS_TEST.md          14 concrete findings from hand-compiling these 26
                        atoms, plus a coverage table against the 20 proposed
                        failure dimensions (~13/20 hit, ~7/20 still untested).
```

## Design decisions carried over from the rest of this project

- **`context` must never encode publication chronology or belief-revision
  history** (only genuine world-conditions: regime, phase, value ranges).
  Direct consequence of the BatchNorm ORIG/REVISED lesson: conflating the two
  turns a real contradiction into a fake COMPATIBLE-via-different-era split.
- **Specialization lives in `quantification[].type`** (Copper vs Metal vs
  Material), not in the predicate name — same principle as the physics/ML
  benchmarks' ENTAILS chains.
- **Deliberately no `GENERALIZES_METHOD`, `COMPOSES_TO`, causal-edge types,
  or ontology beyond what examples forced.** Per the explicit decision to
  derive the relation algebra from real failures rather than design a
  vocabulary upfront -- this is why the predicate list is only 7 names and
  visibly insufficient (see STRESS_TEST.md).

## Run it

```bash
python validate_examples.py
```

## Status

This is the "try to break it" step, not the compiler. 14 concrete
representational gaps were found, the sharpest being: no recursive
proposition-as-term (breaks any real logical implication), no
distinction between functional and set-valued predicate roles (breaks
automatic contradiction derivation for some but not all HOLDS-shaped
claims), and a real scope boundary on context-based reconciliation
(works when one formal quantity varies by regime, fails when natural
language maps one word onto two different formal quantities -- the
relativity case). None of these are patched here. Compiler v0.1 and any
schema revision should be scoped against this list, not built blind.
