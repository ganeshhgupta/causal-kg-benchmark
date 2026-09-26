# K-IR v0.2 — changelog and stress test

## Why the shape changed mid-build

v0.2 started as a narrow patch: add `Concept.resolution_status`, a four-valued
epistemic status, an `Evidence.status` flag, and one concept-split example —
just enough for the 6 "particularly dangerous" cases. That version was written
and then discarded, because a mid-build review made a better argument:

> Do not implement all 130 edge cases. Implement the few meta-primitives that
> make the other 130 expressible later.

The narrow patch bolted fields onto the v0.1 `Proposition`. It would have needed
another schema change for the next class of knowledge (fiction, reference
frames, theory-dependence, belief). So v0.2 was rebuilt around **8 universal
objects** instead:

```
SYMBOL ──────┬──> PROPOSITION ──── CONTEXT
(concepts &  │         │
 relations)  │         ├──> ASSERTION ──── source
             │         ├──> EVIDENCE
             │         └──> DERIVATION ──> other PROPOSITIONs
             │
             └──> REVISION (append-only operation log)

evidence + derivations ──> EPISTEMIC STATUS (computed, never asserted)
```

This was adopted on the merits, not deferred to: three of its pieces map
directly onto failures **already recorded** in `kir-v0.1/STRESS_TEST.md`, so it
is a refactor validated against known breaks rather than speculative ontology
design. It is not the Cyc trap: the core still knows no concepts and no
relations, only how to hold them.

## One correction to the proposed design

The review listed `relativity reference frame → Context(reference_frame=...)`
as a case the generic context handles. **That is wrong, and it is the exact bug
v0.1 Finding 12 warns about.** "No massive object exceeds c locally" and
"galaxies can recede faster than c" do not involve one quantity under two
contexts; they involve two *different formal quantities*
(`LocalPeculiarVelocity` vs `CosmologicalRecessionRate`) that English spells
with one word. Reconciling them via a context key would invent a regime split
with no physical referent. That case is fixed at **symbol resolution** time, not
context time — and v0.2 now has separate machinery for each, which is the
`P-BANK-2` vs water/dropout distinction called out in the examples.

The fiction example (`world=SherlockHolmesCanon`) is used to demonstrate the
generic-context payoff instead, because it genuinely is one.

## What changed, concretely

| v0.1 | v0.2 |
|---|---|
| `predicate` was an unvalidated bare string | `predicate` references a `Symbol` of `kind=RELATION`; inventing vocabulary is now a visible, inspectable, `PROVISIONAL`-markable object |
| relations had no metadata | `Symbol.functional` (true/false/null) declares single- vs set-valued roles |
| `Context` had 7 fixed fields | `Context` is a list of `(key, op, value)` constraints — `world`, `theory`, `reference_frame`, `software_version` need no schema change |
| truth, source and confidence lived on the `Proposition` | `Proposition` is content only; `Assertion` / `Evidence` / `EpistemicStatus` hold the rest |
| "paper X claims Y" was smuggled into `provenance` | `Assertion` is a first-class object with `stance` (including `neutral_report`) and its own `status` |
| multi-premise composition lived in an ad-hoc `hyperedges.json` outside the schema | `Derivation` is a K-IR object with `premises`/`conclusion`/`relation`/`rule`/`theory`/`context`/`status` |
| no concept lifecycle | `Symbol.resolution_status` ∈ {RESOLVED, PROVISIONAL, AMBIGUOUS, UNRESOLVED_PARENT} |
| no history | `RevisionEvent` append-only log: CREATE/MERGE/SPLIT/SUPERSEDE/RETRACT/CORRECT/REFINE_CONTEXT/RETYPE_RELATION/INVALIDATE_PROOF/RESTORE |
| validator only checked JSON structure | validator also checks referential integrity, predicate typing, and **independently recomputes** epistemic status from evidence |

## The 6 dangerous cases

| # | Case | Mechanism | Status |
|---|---|---|---|
| 1 | Parent concept doesn't exist (chlorophyll) | `Symbol.resolution_status=UNRESOLVED_PARENT` + `RevisionEvent(CREATE)` | **Handled.** `P-CHLOROPHYLL` is well-formed and SUPPORTED with both symbols unresolved — concept resolution and epistemic status are independent axes |
| 2 | Neither provable nor refutable (dark matter) | `EpistemicStatus=UNRESOLVED` | **Partially handled, and the example breaks it on purpose** — see Finding 1 |
| 3 | Both supported and refuted (two RCTs) | `EpistemicStatus=INCONSISTENT`, never auto-resolved | **Handled.** `P-COMPOUND-X` |
| 4 | Concept must be split after ingestion | `RevisionEvent(SPLIT)` + `reassignments` | **Handled.** `REV-002`; proposition ids stay stable, only argument references move |
| 5 | Previously-merged things must separate | same as 4 | **Handled**, and distinguished from the context-based fix (see the correction above) |
| 6 | Proof invalidation from retraction | `Evidence.status=retracted` + `Derivation.status=invalid` + `RevisionEvent(RETRACT/INVALIDATE_PROOF)` | **One hop handled, deeper chains not.** See Finding 2 |

## v0.1 gaps this shape closed as a side effect

- **Finding 4 + Finding 10 (functional vs set-valued roles).** `R-PRIMARY_MECHANISM.functional=true`
  makes the BatchNorm ICS-vs-smoothing contradiction *mechanically derivable*, like
  `x=3` vs `x=5`. `R-GUARANTEES.functional=false` is the control: the structurally
  identical TCP pair yields **no** contradiction, correctly, because a protocol
  guarantees many things at once. The false TCP claim is rejected by its own
  refuting evidence instead. Both are in the examples, side by side, so the flag
  is doing observable work.
- **Finding 6, implication half.** `Differentiable(f) ⟹ Continuous(f)` is now
  `D-DIFF-CONT`, a `Derivation` between two ordinary propositions, instead of an
  invented `IMPLIES` predicate over faked function terms. Propositional attitudes
  ("Alice believes P") are still not representable — `Assertion` covers only the
  narrow source-claims-P case.
- **Finding 0, partially.** Predicates are still open-world, but now resolve to
  registered `Symbol`s, so vocabulary invented on the fly is visible
  (`R-UPDATE_RULE_OF` is marked `PROVISIONAL` for exactly this reason) rather
  than silently indistinguishable from reviewed vocabulary.

## Findings from building this (new, unfixed)

**1. The four-valued model is too coarse for degree/quantity claims.**
`P-DARKMATTER` has one active supporting observation (microlensing, consistent
with *some* PBH fraction in narrow mass windows) and one active refuting one
(CMB/LSS constraints ruling out PBHs as the *dominant* component). The rule
computes INCONSISTENT. The real situation is neither INCONSISTENT nor
UNRESOLVED: the two observations are about different *quantities*, and the
proposition has an implicit all/some/none that the representation does not
carry. `R-COMPOSED_OF.functional` is therefore `null` — deliberately
unclassifiable. Left broken in the data rather than swapped for a cleaner
example. Contrast `P-COMPOUND-X`, where INCONSISTENT is genuinely correct; the
pair is what shows INCONSISTENT is a real state and not a dumping ground.

**2. "Evidence is active" is not the same as "evidence is admissible" — caught by the validator, not by inspection.**
The first version of this changelog claimed `P-PROTOCOL-Z` demonstrated stale
downstream status. `validate_examples.py` disproved that: the retraction of
`EV-Z-EXPERIMENT` left `EV-PROTOCOL-DERIVED` sitting at `status=active`, so the
naive rule reported SUPPORTED and there was *nothing to detect*. The fix was to
the specification, not the claim: admissible evidence now also requires that
`derivation_result` evidence came from a `Derivation` with `status=valid`. The
validator runs both rules and diffs them, which is what makes the collapse
visible:

```
P-PROTOCOL-Z: naive rule says SUPPORTED, derivation-aware rule says UNRESOLVED
```

Still unfixed: chains deeper than one hop, and the fact that nothing
*automatically* recomputes stored status. `P-PROTOCOL-Z`'s stored value is left
wrong on purpose, and the validator asserts that it stays wrong, so the
limitation cannot silently disappear.

**3. `EpistemicStatus` is underspecified: it cannot see derived contradictions.**
Its rule is defined purely over evidence counts, so the CONTRADICTS derivable
from `R-PRIMARY_MECHANISM.functional=true` is invisible to it. `P-BN-ICS` is
recorded as INCONSISTENT while the rule says REFUTED. Both are defensible and
they measure different things, which is the problem — the status needs to be a
function of evidence *and* derived structural contradictions. Recorded, not
patched.

**4. `EpistemicStatus` carries no context marker.**
`P-HOLMES-221B` is SUPPORTED *within* `world=SherlockHolmesCanon`, but the
status entry itself inherits the context only by reference to the proposition. A
query that ignores context reads it as a plain real-world truth.

**5. Generic `Context` fixes storage, not inference — stated rather than glossed.**
A `world` or `theory` key needs no schema change, which is the real win. But
nothing in v0.2 defines what may be inferred *within* or *across* a context
boundary. Two propositions under `phase=liquid` compose; two under
`world=Fiction` and `world=actual` must not. Nothing prevents a naive reasoner
from chaining `P-HOLMES-221B` with `P-221B-MUSEUM` and concluding a fictional
detective lives in a real museum.

## Addressed vs deferred, against the 10 structural-break categories

| Category | v0.2 |
|---|---|
| Unknown concept / missing parent | **Addressed** — `Symbol.resolution_status` |
| Unknown / unprovable truth value | **Addressed for binary claims**, broken for degree claims (Finding 1) |
| Both true and false (real disagreement) | **Addressed** — `INCONSISTENT` + separate `Assertion`s |
| Concept split / previously-merged-must-separate | **Addressed** — `RevisionEvent(SPLIT)` |
| Non-monotonic invalidation / retraction | **One hop addressed**, deeper chains and auto-recomputation deferred (Finding 2) |
| Unknown relation type | **Addressed structurally** — relations are `Symbol`s; adding one is data, not schema |
| Composition that isn't logical entailment | **Addressed** — `Derivation.relation` + `rule` + `status` |
| Fiction / counterfactual / belief / modal | **Storage addressed** (`Context` keys, `Assertion`); **inference rules deferred** (Finding 5); propositional attitudes still unrepresentable |
| Numeric probability, uncertainty, confidence intervals | **Deferred.** `Evidence.independence_group` is the only hook; no distributions, no intervals, no degrees |
| Temporal identity / versioning | **Partially** — `RevisionEvent` is an operation log, not bitemporal identity; "the same entity at two times" is still unmodelled |
| Axiom-system dependence | **Recorded, not checked** — `Derivation.theory` stores the dependency; nothing validates a proof against an axiom set |

Also still deferred, unchanged from the stated scope: rich causality (OR-causes,
overdetermination, prevention, mediators), and an actual append-only storage
engine (the `RevisionEvent` log is the record format, not the store).

## Run it

```bash
python validate_examples.py
```

Current result: structure, references and predicate typing clean across 18
propositions / 18 assertions / 15 evidence / 3 derivations / 4 revisions, with
exactly 2 epistemic divergences, both asserted-as-expected by the validator so
the documented limitations cannot quietly vanish.
