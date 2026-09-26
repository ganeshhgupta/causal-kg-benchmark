# K-IR v0.1 Stress Test

26 hand-compiled atoms (`examples.json`) against `kir-schema.json`: physics/ML
"nastiest cases" (Copper/Metal specialization, water 0-4C, Dropout
train/inference, BatchNorm's two hypotheses, DropConnect/Dropout) plus a
deliberately cross-domain batch (math, probability, algorithms, distributed
systems, networking, relativity) chosen specifically to get away from
metal/temperature/water and test structurally different failure modes.

**Meta-result: all 26/26 pass schema validation.** That is itself the first
finding, not a clean bill of health — see Finding 0.

## Finding 0 (meta): schema validation is nearly toothless as currently written

`predicate` is `{"type": "string"}` with no enum. Every made-up predicate
name invented on the spot during compilation (`IMPLIES`,
`OBSERVATIONALLY_EQUIVALENT_TO`, `EXECUTES_SEQUENTIALLY`, `BOUNDED_ABOVE_BY`)
validated cleanly, because nothing constrains the vocabulary. Structural
validation (are the required fields present, is a Term well-formed) is not
the same problem as semantic adequacy (does the vocabulary actually cover
what's needed), and v0.1 currently only tests the former. A v0.2 might want
either a closed enum (defeats extensibility) or a registered/versioned
predicate list with an explicit "unregistered predicate" warning, so
inventing vocabulary on the fly is visible rather than silent.

## Findings from the physics/ML batch (KIR-001 to KIR-014)

**1. `context.entity_type` vs `quantification[].type` redundancy.**
Specialization (Copper -> Metal -> Material) structurally lives in
`quantification[].type`, but `context.entity_type` exists as a second,
overlapping place to express the same kind of restriction. Never
disambiguated which one wins if both are present. (KIR-001/002/003)

**2. Conjunctive claims don't fit a single-predicate atom.**
"Dropout masks activations AND prevents co-adaptation AND acts as an
implicit ensemble" (M041) is three claims in one sentence. v0.1 forces
picking one (the mechanistic core) and dropping the other two, or splitting
into multiple atoms with no explicit link between them. (KIR-010)

**3. GENERALIZES has no structural representation — only assertable, not derivable.**
DropConnect (masks weights) generalizing Dropout (masks activations) is a
fact about the DEFINITIONS of the two function symbols (`Activation(u)` is
what you get when you mask all of `Weight(u,*)`), not something derivable
from the two atoms as given. Needs a `Definition`/derivation construct
connecting function symbols; without it, GENERALIZES stays a hand-asserted
pairwise judgment exactly like the P02 problem in the ML benchmark — the
representation didn't fix the problem, it just re-hosted it. (KIR-010, KIR-012)

**4. Mechanism-attribution claims have no dedicated predicate — but a positive result hides inside this.**
"X's primary mechanism is Y" (BatchNorm) doesn't fit MONOTONIC / EQUALS /
SUBTYPE_OF / etc., so it got forced into `HOLDS(PrimaryMechanism(BatchNorm),
<bare string>)`. **But**: if a predicate's role is declared FUNCTIONAL
(single-valued), CONTRADICTS between two HOLDS atoms with the same subject
and different values becomes MECHANICALLY DERIVABLE — no hand-labeling
needed, the same way `x=3` and `x=5` are contradictory because `=` is
functional. v0.1 has no field to declare this. Worth building — see Finding 10
for why it doesn't generalize for free. (KIR-013, KIR-014)

**5. Value-domain bounds can't be function-dependent.**
`Temperature(x) < BoilingPoint(x)` needs `BoilingPoint(x)` as the upper
bound — but `ValueDomainConstraint.max` only accepts `number|string|null`.
Had to store it as the bare string `"boiling_point(x)"`, losing its
structure as a term. Common in physics (any bound that depends on the same
or another individual). (KIR-008)

## Findings from the cross-domain batch (KIR-015 to KIR-024B)

**6. No recursive Proposition-as-Term — breaks any real logical implication (the single worst break found).**
"Differentiable(f) implies Continuous(f)" needs `Differentiable(f)` and
`Continuous(f)` to be TRUTH-VALUED propositions used as arguments to
`IMPLIES` — but `Term` only has variable/constant/function (value-returning).
It gets worse one level down: "Independent(X,Y) implies Cov(X,Y)=0" needs
the CONSEQUENT to be a full nested EQUALS proposition
(`Covariance(X,Y) = 0`), not just a term. Had to fake it with a made-up
function name `CovarianceIsZero(X,Y)` standing in for the real nested
proposition. This is the deepest structural gap in v0.1: no recursion, no
higher-order embedding, so any statement whose content is itself a claim
about other claims cannot be represented faithfully. (KIR-016, KIR-021)

**7. "Which statistic/measure" is a distinct axis from context, and v0.1 has no field for it.**
"Hash lookup is expected O(1)" vs "hash lookup is O(1)" (unqualified, and
arguably false read as worst-case) differ in which AGGREGATION of a random
runtime is being reported (expected / worst-case / amortized / best-case) —
not a world-condition like phase or regime. Got smuggled into
`context.assumptions` as free text, indistinguishable there from an
ordinary background condition. Needs its own field, likely attached to the
specific argument, not the whole atom's context. (KIR-017, KIR-018)

**8. New predicate categories keep appearing per domain — the "small fixed core" is already too small.**
`OBSERVATIONALLY_EQUIVALENT_TO` (serializability: outcome-equivalent to some
serial order) and `EXECUTES_SEQUENTIALLY` (literal execution order) are
definitionally different relations with near-identical English phrasing
("behaves as serial" vs "runs serially") and NEITHER fits any of v0.1's 7
predicates. Confirms the instinct not to design vocabulary upfront, but also
shows 7 predicates didn't survive contact with even ~10 non-physics
examples. (KIR-019, KIR-020)

**9. "CONTRADICTS" is conflating two different situations — this is a calculus problem, not just a K-IR problem.**
The TCP and serializability examples are NOT genuine logical contradictions
the way BatchNorm's two hypotheses are. TCP "provides an ordered byte
stream" (true) and "preserves message boundaries" (false) are two DIFFERENT
properties, one of which happens to be false — not one functional role
taking two incompatible values. The right model is: `UNRELATED` predicates
+ a separate per-atom TRUTH/admission judgment (the false one gets rejected
by the evidence layer, never enters the KG), NOT a pairwise `CONTRADICTS`
edge between the two atoms. The six-relation calculus itself needs this
sharpened, independent of any K-IR schema fix. (KIR-020 vs KIR-019, KIR-023 vs KIR-022)

**10. Not every `HOLDS(Role(subject), value)` shape is functional — Finding 4's trick doesn't generalize for free.**
`Guarantees(TCP)` looks structurally identical to `PrimaryMechanism(BatchNorm)`
but is SET-VALUED (a protocol guarantees many properties at once), not
single-valued. Two `HOLDS(Guarantees(TCP), P)` atoms with different `P` are
NOT automatically contradictory. v0.1 has no way to declare a role
functional vs set-valued, so Finding 4's auto-derivation trick is unsafe to
apply blindly. (KIR-022, KIR-023)

**11. `provenance.confidence` has no value for "flatly false, never actually the accepted view."**
`contested` and `superseded` both imply the claim was once a genuine
mainstream position. A common misconception (TCP preserving message
boundaries) was never that. Missing enum value, e.g. `refuted`. (KIR-020, KIR-023)

**12. Context-based reconciliation has a real scope boundary — arguably the most important finding overall.**
The strategy that cleanly resolved every earlier "apparent contradiction"
(water, dropout, attention: same formal quantity, different regime/phase/
value-range) does NOT work for the relativity case. "Velocity" in "no
massive object exceeds c locally" and "galaxies can recede faster than c"
maps to two ENTIRELY DIFFERENT formal quantities (`LocalPeculiarVelocity`
vs `CosmologicalRecessionRate`), not one shared symbol under different
conditions. A compiler that tried to reconcile this via context (the way it
correctly handles water) would either invent a fake regime split with no
physical referent, or fail to unify them and miss that these are genuinely
`COMPATIBLE`. This has to be solved at SYMBOL RESOLUTION time (which formal
quantity does this English word mean here), before context-matching is
even applicable — a compiler-frontend requirement, not a schema field.
(KIR-024A, KIR-024B)

**13. Quantification is often genuinely unstated in the source, and the schema has no way to say "unspecified."**
"x^2 = 4" doesn't state whether it's `forall x` (false), `exists x` (true,
loses the `x=-2` branch if naively rewritten to `x=2`), or a constraint
defining a solution set. Forcing an explicit `quantification` array onto
every atom means the compiler must guess intent the source never stated,
with no way to flag the guess as uncertain. (Not compiled as an atom --
noted as a gap since it surfaced during the hash-lookup ambiguity case.)

**14. Compiler requirement, not a schema gap: rewrites must preserve solution sets.**
Rewriting "x^2=4" to "x=2" is syntactically tempting and drops the `x=-2`
branch. Not a representation problem (both forms are individually
representable) — a hard requirement on whatever canonicalization engine
manipulates K-IR atoms later, worth recording now so it isn't rediscovered
the hard way.

## Coverage against the 20 proposed failure dimensions

| # | Dimension | Status |
|---|---|---|
| 1 | Quantifier failure (some/all/most) | Partial — Finding 13 |
| 2 | Direction reversal (A→B vs B→A) | **Hit cleanly** — KIR-016, KIR-021 |
| 3 | Missing modality (may/must/usually/always) | **Already handled well** — `modality` enum |
| 4 | Expected vs worst-case | **Hit hard** — Finding 7 |
| 5 | Local vs global | **Hit hard** — KIR-024 |
| 6 | Definition vs causal claim | Partial — Finding 4/9 |
| 7 | Observational equivalence vs literal identity | **Hit hard** — Finding 8 |
| 8 | Mechanism vs outcome | Partial — BatchNorm/Finding 4 |
| 9 | Necessary vs sufficient condition | **Not tested** — gap |
| 10 | Scalar vs vector / magnitude vs direction | **Not tested** — gap |
| 11 | Temporal ordering (before/during/after) | Partial — `phase` field only |
| 12 | Statistical association vs causation | **Not tested** — gap |
| 13 | Approximation vs exact equality | **Not tested** — gap |
| 14 | Discrete vs continuous regime | Partial — water's value_domain |
| 15 | Algorithm vs implementation | Decent — Finding 7/8 |
| 16 | Object-level claim vs claim-about-a-paper | **Already handled well** — provenance/BN split |
| 17 | Single-valued vs set-valued result | **Hit hard** — Finding 10 |
| 18 | Closed-world vs open-world assumption | **Not tested** — gap (related to DISJOINT facts) |
| 19 | Deterministic vs probabilistic statement | Decent — KIR-017, KIR-021 |
| 20 | Composition (A+B jointly imply C) | **Not tested in this schema at all** — no hyperedge/multi-premise construct exists in v0.1 (same gap as physics/ML H01, never addressed here) |

**Net: ~7/20 genuinely untested.** That's the honest input for what the next
batch of examples should target, per the instruction to derive the next
100-300 propositions from actual failures rather than designing coverage
upfront.

## What I would NOT do yet

Per the standing instruction: not adding `GENERALIZES_METHOD`, `IMPLIES`,
`OBSERVATIONALLY_EQUIVALENT_TO`, a `functional`/`set-valued` flag, or
recursive Proposition-as-Term to the schema in this pass, even though
several are clearly needed. The point of this exercise was to find where
v0.1 breaks with real examples, not to patch it reactively example-by-example
into a v0.2 nobody stress-tested. That's the next round.
