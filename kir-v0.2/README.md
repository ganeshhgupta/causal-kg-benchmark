# K-IR v0.2

v0.1 made the representation explicit and then broke it on purpose (14 findings).
v0.2 restructures it around **8 universal objects** so that new *kinds* of
knowledge become data rather than schema changes, and uses that shape to handle
the 6 "particularly dangerous" cases: unknown concepts, unprovable claims,
genuine disagreement, concept splits, re-separation, and retraction.

```
kir-v0.2/
├── kir-schema-v0.2.json   Symbol / Proposition / Context / Assertion /
│                          Evidence / Derivation / EpistemicStatus /
│                          RevisionEvent
├── examples-v0.2.json     18 propositions across biology, cosmology, medicine,
│                          lexical ambiguity, ML, networking, real analysis and
│                          fiction; 3 derivations, 4 revision events
├── validate_examples.py   Structure + referential integrity + predicate typing
│                          + independent epistemic recomputation
└── CHANGELOG.md           Why the shape changed mid-build, what each dangerous
                           case demonstrates, 5 new unfixed findings, and the
                           addressed-vs-deferred table
```

## The one-line version of each object

| Object | Holds |
|---|---|
| `Symbol` | anything referenceable — concepts *and* relations, with a lifecycle (`resolution_status`) and, for relations, `functional` (single- vs set-valued) |
| `Proposition` | semantic content only: predicate, arguments, quantification, polarity, modality, context. No truth, no source, no confidence |
| `Context` | an open list of `(key, op, value)` constraints — `phase`, `regime`, `theory`, `world`, `reference_frame`, whatever, with no schema change |
| `Assertion` | "source S claims P", with `stance` (`supports`/`refutes`/`neutral_report`) and its own retraction status |
| `Evidence` | a specific experiment/observation/derivation bearing on P, separately retractable |
| `Derivation` | multi-premise inference, with `relation` (ENTAILS vs COMPOSES_TO), `rule`, `theory`, `context`, `status` |
| `EpistemicStatus` | SUPPORTED / REFUTED / UNRESOLVED / INCONSISTENT — **computed** from admissible evidence, never asserted |
| `RevisionEvent` | append-only log of CREATE / MERGE / SPLIT / RETRACT / INVALIDATE_PROOF / … |

## Run it

```bash
python validate_examples.py
```

## Status

Everything validates, and the validator has real teeth this time: it resolves
every id reference, checks that each predicate is actually a `RELATION` symbol,
and recomputes epistemic status independently under two rules to catch the
retraction case. It already earned its keep — it disproved a claim in the first
draft of `CHANGELOG.md` and forced a fix to the status *specification* rather
than the prose.

Two divergences remain in the data on purpose, and the validator asserts they
stay there so the limitations cannot quietly vanish: a stale downstream status
(nothing auto-recomputes transitively), and an INCONSISTENT marker that an
evidence-count rule cannot see.

Five new findings are recorded and unfixed, the sharpest being that the
four-valued epistemic model is too coarse for any claim with an implicit
all/some/none quantity (the dark matter case), and that generalizing `Context`
fixes *storage* of fiction/theory/frame contexts without defining what may be
inferred across a context boundary. Those are the input for v0.3, not something
to patch reactively now.
