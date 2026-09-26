# Loop log

One entry per cycle of `real papers -> extract/compile -> reason -> compare with
gold -> fix ONLY the failure`. The point of the log is that a fix is only
legitimate if a measured failure preceded it, so each entry names the failure
first and the change second.

## Scoreboard against the stated targets

Reproduce everything with one command: `python eval/run_all.py`. It gates on the
checks that must not regress, reports the advisory ones, and deliberately does
NOT run any LLM baseline, because those cost money and should be an explicit
opt-in rather than something a "run everything" script silently bills for.

| target | required | measured | verdict |
|---|---|---|---|
| canonical proposition matching F1 | >= 0.95 | 1.000 on shared-vocabulary pairs; cross-vocabulary **6/15 claims matched** (was 0/15) | **PARTIAL, see cycles 5-6** |
| dangerous false merges | < 0.005 | 0.0000 | PASS |
| end-to-end claim recall (blind extraction) | n/a | 1.000 | measured |
| end-to-end answer accuracy (blind extraction) | n/a | 0.833 | measured |
| hallucinated claims (blind extraction) | < 0.005 | 0.0000 | PASS |
| retraction propagation precision | >= 0.95 | 1.0000 (n=14, 3 chains, 2 domains) | PASS |
| retraction propagation recall | >= 0.95 | 1.0000 (n=14, 3 chains, 2 domains) | PASS |
| contradiction detection recall | >= 0.95 | 1.0000 | PASS, evidence-level only |
| false contradiction rate | < 0.01 | 0.0000 | PASS, detector rarely fires |
| proof-chain validity | >= 0.99 | 1.0000 | PASS |
| hallucinated proof steps | < 0.005 | 0.0000 | PASS |
| epistemic classification macro-F1 | >= 0.95 | 1.0000 (n=14, 3 chains, 2 domains) | PASS |
| schema growth: new semantic fields needed by a 3rd chain in a 2nd domain | flat | **0** (one documentation-parity field) | PASS |
| margin over LLM+RAG | >= 10 pts | **unmeasured** | **BLOCKED** |
| margin over best non-LLM baseline | n/a | +16.7 pts | measured |

**How much to trust this.** The reasoner rows are over n=14 gold claims on three
real chains in two domains, on hand-authored graphs. The compiler stage has run
once, on one paper, blind (cycle 5), which is where the end-to-end rows come from;
one paper is not a sample. The honest readings are the partial row
(canonicalization works within a shared vocabulary and reaches 6/15 across
independently invented ones) and the blocked row.

Three passes carry scope caveats stated where they are measured rather than
buried: false merges are 0 because the pipeline never merges anything;
contradiction recall covers evidence-level conflict, which INCONSISTENT status
already encodes, while structural contradiction is untested because neither real
corpus contains a functional relation with a qualifying pair; and the +16.7 point
margin is one claim's difference at n=6.

---

## Cycle 1 (2026-09-26): reason and compare, on real data

**Corpus.** Fujii et al. PONV literature, the largest retraction case on record.
6 claims. Gold labels come from Carlisle JB, *Anaesthesia* 2012;67:1076-1090
(PMID 22734848), which pools Fujii trials separately from other authors' and
states what survives exclusion. Verified via the Europe PMC API after PubMed
CAPTCHA-blocked and Wiley returned 403.

**Result.** 6/6 exact match, zero false collapses, zero UNRESOLVED/REFUTED
conflation.

**Honest limitation.** The graph and the gold labels were written by the same
author, so this validates the reasoner's logic, not the pipeline. A blind LLM
extraction could not be run: spawning a fresh no-context subagent needs
tmux/WSL, which is unavailable here, and a context-inheriting fork would already
have seen the gold labels, making a "blind" result worthless. Rather than fake
one, cycle 1 measured extraction sensitivity instead (below).

**Failure found in the data, not the code.** Carlisle reports that antiemetic
synergism was supported only by the Fujii trials while other authors found
*antagonism*. So that claim is INCONSISTENT before the retraction and REFUTED
after: the retraction **resolves a conflict** rather than destroying support.
The original task spec had four outcome classes and none of them fit.

**Fix.** Added `RESOLVED_INCONSISTENCY` as a fifth outcome class. Earned by real
data on the first real chain.

**Second finding, recorded not fixed.** Granisetron survives exclusion but with
its effect "greatly reduced". "Still true, much smaller" is not representable in
K-IR v0.3, so the gold label is correct about the epistemic state and silent
about magnitude. This is the predicted "two claims differ only by quantity"
failure, arriving immediately. Quantity semantics is now earned but not yet
built.

---

## Cycle 2 (2026-09-26): compiler-error sensitivity

**Method.** `eval/robustness_eval.py` applies each mistake a real compiler
plausibly makes to the reference graph and scores the consequence against gold.
Predictions about which mutations are survivable were written before running.

**Results.**

| simulated compiler error | recall | precision | false survival | verdict |
|---|---|---|---|---|
| baseline | 1.00 | 1.00 | 0 | correct |
| false_merge | 0.83 | 1.00 | 0 | claim disappears entirely |
| split_same_claim | 1.00 | 0.86 | 0 | phantom twin absorbs half the evidence |
| drop_refuting_evidence | 0.67 | 1.00 | 0 | REFUTED degraded to UNRESOLVED |
| wrong_stance_on_null | 0.67 | 1.00 | **2** | **dangerous** |
| no_independence_group | n/a | n/a | n/a | query not expressible at all |
| prebake_retraction | 0.33 | 1.00 | 0 | right status, cannot say what changed |

**Two defects found in my own evaluator, which is why the first run's numbers
were wrong.**

1. `split_same_claim` scored a perfect 1.00. Splitting one claim into a phantom
   twin that absorbs the Fujii evidence left the gold claim looking healthy, and
   the metric only counted gold claims matched, so inventing spurious claims was
   free. **Fix:** report precision and a spurious count, and exclude any run with
   spurious propositions from "survived intact". Same shape of hole as the
   headline-gaming bugs found in the earlier canonicalization scorer.

2. `wrong_stance_on_null` was scored as **safe**. The danger metrics were defined
   over transition *classes* against a hardcoded collapse set, so "gold says
   REFUTED, system reports SUPPORTED" matched neither and vanished. That is the
   most misleading error the system can make. **Fix:** define danger on the
   answer (the after-status), not the transition class, in both
   `robustness_eval.py` and `retraction_eval.py`.

After the fixes, measured results match the pre-registered predictions: only
baseline survives intact, and `wrong_stance_on_null` is the sole dangerous
failure.

**Fix targeted at the dangerous failure only.** `compiler/lint_evidence.py`
flags evidence whose source text reads as a null or negative finding while its
stance is `supports`, plus the two failures that make a graph unusable rather
than merely wrong (pre-baked retraction, no independence grouping). Verified:
clean on the real corpus (no false positives), catches all three targeted
mutations, and correctly silent on `false_merge`, `split_same_claim` and
`drop_refuting_evidence` because those need semantic judgement or the source text
rather than a keyword rule. Not pretending otherwise is the point.

---

## Cycle 3 (2026-09-26): baselines, and a real depth-2 chain

**Baselines measured.** `eval/baselines/naive_baselines.py`. These are NOT LLM
baselines; they are the non-LLM methods the field currently uses, plus two
heuristics that mimic specific LLM reading errors.

| method | accuracy | false survival | false collapse |
|---|---|---|---|
| citation_cascade (the prior art: cite it, lose it) | 0.333 | 0 | 2 |
| stance_blind_survivors (literature still exists, so it stands) | 0.667 | **2** | 0 |
| recency_wins (trust the newest source) | 0.833 | 0 | 1 |
| **kir_reasoner** | **1.000** | **0** | **0** |

Margin over the best non-LLM baseline: **+16.7 points**. Two honest caveats.
With n=6 that margin is literally one claim, so it is directional, not
significant. And `recency_wins` scores well partly by luck: the newest assertion
on the contested claims happens to be Carlisle's refutation.

**Real depth-2 chain acquired.** The depth-1 limitation is closed. Fujii's own
2002 review, *Combination Antiemetic Regimens for Prevention of PONV* (PMID
29492850), was retracted (notice PMID 29705919) **because its constituent trials
were retracted**, and the notice scopes the damage to named tables and sections.
That is documented derived-support collapse, which is exactly the capability
under test. Encoded with the review's own synthesis step as a `Derivation`
(relation GENERALIZES, validity UNVERIFIED, since a narrative review
generalising from its trials is not entailment). Result: 4/4 exact match, with
the level-2 synthesised principle correctly reaching REFUTED rather than merely
UNRESOLVED, because Carlisle's independent evidence bears against it.

Combined: **10/10 across two real chains**, zero false survivals.

**Failure found by the real data, in the query interface.** Running
`--retract-source "Fujii"` also retracted Carlisle's refuting evidence, whose
source text reads "trials by authors **other than** Fujii". The wrong side was
retracted and the answer silently degraded from REFUTED to UNRESOLVED. This is
the normal case rather than an edge case: re-analysis papers routinely describe
their evidence by contrast to the author under suspicion.

**Fix.** Added `--retract-group`, which selects by `independence_group`, and made
`--retract-source` refuse outright when its match spans more than one
independence group, printing every match with its group. A wrong answer is worse
than no answer here, so it errors rather than guesses.

**Finding recorded, not fixed.** Adding a second corpus immediately produced the
same claim twice under different ids: `P-SYNERGISM` in the PONV corpus and
`P-MULTI-RECEPTOR-PRINCIPLE` in the review corpus are the same proposition
reached from two documents. Nothing in the pipeline notices. This is the
canonicalization problem arriving for real on the second corpus, and it is the
strongest argument for the canonicalization stage that does not yet exist.

---

## Cycle 4 (2026-09-26): measuring the targets that need no LLM

Four stated targets were measurable without a compiler or a baseline, so they
were measured rather than left as prose.

### Proof-chain validity and hallucinated steps

`eval/proof_validity.py` walks every proof the engine returns, before and after
retraction, over both real corpora and the fixture, and checks each step against
the graph: does the named derivation exist, does it conclude what the step
claims, are the trace's premises exactly the derivation's premises, does every
cited evidence item exist and actually attach to that proposition with
stance=supports.

**First run failed at 0.857 validity.** The engine returned a completely
well-formed support-proof for `P-SYNERGISM` while that claim's status was
INCONSISTENT, with nothing in the output disclosing the conflict.

Two things were wrong, one in the auditor and one in the engine.

- *Auditor:* its rule was "only SUPPORTED claims may have proofs". Wrong.
  INCONSISTENT means supported AND refuted, so the support side has a real proof.
  The requirement is that the proof **disclose** the conflict, not be withheld.
- *Engine:* a support-proof for a contested claim was indistinguishable from a
  proof that the matter is settled. Fixed by putting `status`, `contested` and
  `counter_evidence` on every trace node, plus `rests_on_contested`, which
  propagates upward so a chain resting on a contested premise cannot look clean
  at the top. Asking "why is this true" and getting an unqualified proof of a
  disputed claim is misleading even when every step checks out.

| target | measured | verdict |
|---|---|---|
| proof-chain validity >= 0.99 | **1.0000** (26 steps) | PASS |
| hallucinated steps < 0.005 | **0.0000** | PASS |

### Canonical claim matching and false merges

`eval/canonicalization_eval.py`, on 7 real claim pairs across the two corpora:
the genuine cross-document duplicate cycle 3 found, plus six deliberately
tempting decoys (one drug swapped, a specific instance against the general
principle it instantiates, the same drug in opposite directions).

| matcher | F1 | false_merge_rate | gate |
|---|---|---|---|
| never_merge (what the pipeline does today) | 0.000 | 0.000 | PASS |
| exact_structural | 0.000 | 0.000 | PASS |
| lexical_overlap@0.5 | 0.000 | 0.167 | FAIL |
| same_predicate | 0.000 | 0.500 | FAIL |
| lexical_overlap@0.3 | 0.000 | 0.500 | FAIL |

**No matcher found the real duplicate.** Every TP is zero. The genuine pair
differs in predicate *and* in argument symbols, because it is a cross-document
paraphrase, so structural matching cannot see it and lexical matching only
finds decoys. `lexical_overlap@0.3` merged "PONV is more likely when granisetron
is given alone" with "granisetron is effective" -- opposite directions, the worst
merge available.

Measured position against the targets: canonical matching F1 **0.000** against a
required 0.95, and the only configurations passing the false-merge gate are the
ones that never merge anything. This is the quantified case for a canonicalization
stage, and n=7 makes it a floor to beat, not a result.

---

## What cycle 5 needs

Two of these still need a capability this session does not have:

- **Blind extraction (BLOCKED).** Spawning a fresh no-context subagent requires
  tmux. Diagnosed on 2026-09-26: this `claude` process runs under Windows
  MINGW64/Msys, with `TMUX` unset, tmux absent from PATH and `WSL_DISTRO_NAME`
  unset. A WSL Ubuntu instance is running on the machine and a tmux session
  exists inside it, but this process is not in it, so it cannot reach it. The fix
  is to run `claude` from inside the WSL tmux session (with the repo reached via
  `/mnt/c/...`), not from the Windows terminal. A fork is not a substitute: it
  inherits this session's context including the gold labels, so its result would
  not be blind. Until then the compiler stage is unmeasured and every score in
  this log is about the reasoner, not the pipeline.
- **LLM-only and LLM+RAG baselines (BLOCKED, same reason).** The measured margin
  is over non-LLM methods. No claim about beating an LLM is supported.

Not blocked, just not done:

- **Canonicalization stage.** Earned by cycle 3's duplicate claim across corpora.
- **Quantity semantics.** Earned by cycle 1's "greatly reduced" effect size.
- **Corpus scale.** Two chains, 10 gold claims. The VITALITY study reports 1,330
  retracted trials feeding 847 systematic reviews and 157 guidelines with named
  chains, which is the scale-up target.
- **Q-SATO-BISPHOSPHONATE labels.** Blocked on Grey et al. 2018 (PMID 30133693),
  not open access. Labels deliberately withheld rather than guessed.
- **Deeper than 2.** Real data now reaches depth 2; the engine is tested to
  depth 3 only by fixture.

## Calibration note

Published work on easier claim-relation labeling reports around 0.81 macro-F1,
and SciFact-Open shows ~15-point F1 drops on generalization. Absolute ≥95%
targets are above the state of the art. The two targets worth keeping as hard
gates are the safety ones, because they are properties rather than accuracy
numbers: false merges and false survivals should be zero. The headline should be
the margin over baselines.

---

## Cycle 4 (2026-09-26): the compiler stage actually ran

**Blocker cleared.** Session moved to WSL, tmux 3.6 present, so a fresh
no-context subagent could finally be spawned. The extractor was given only the
Carlisle abstract, the v0.3 schema and `compiler/EXTRACTION_SPEC.md`, and was
explicitly fenced off from the reference graph and gold labels. This is the
first cycle where the compile stage is real rather than simulated.

**Blind extraction result.**

| metric | value |
|---|---|
| claim_recall | 6/6 = 1.000 |
| claim_precision | 6/15 = 0.400 |
| answer_accuracy | 5/6 = 0.833 |
| false_survival | 0 |
| false_collapse | 0 |

The compiler represented every gold claim and produced the right retraction
answer for five of six, with zero dangerous errors. It also independently
grouped the Fujii evidence, which is what makes the query expressible at all.

**Failure 1, in my own scorer, not the extractor.** The first run scored 2/6.
Cause: `eval/extracted_eval.py` selected retraction targets with
`"fujii" in group.lower()`, which also matched the compiler's
`ig_non_fujii_trials`, so the refuting evidence was retracted alongside the
fraudulent evidence. **This is the identical bug fixed in the reasoner CLI one
cycle earlier**, reproduced immediately in new code. Two sites, same mistake.

*Fix:* moved the guard into a shared, tested `author_groups()` helper in
`reasoner/epistemic_query.py` rather than patching the call site. A near-miss
during that fix is worth recording: the first version used `\b(non...)` and
still failed on `ig_non_fujii_trials`, because underscore is a word character
so `\b` never fires. Caught only because the helper was given a test table.

**Failure 2: lint false positive, found by real extracted data.** The compiler
modelled antagonism as its own proposition and attached evidence *supporting*
it. `NULL_RESULT_AS_SUPPORT` fired, because it matched the word "antagonism" in
the source without looking at the claim being supported. *Fix:* the rule now
skips when the negative marker appears in the claim's own wording. Verified it
still catches all three real mis-encodings and is now clean on all three graphs.

**Disputed gold label, deliberately not changed.** The single answer mismatch is
`P-GRANI-ALONE-WORSE`: gold UNRESOLVED, extraction REFUTED. The compiler treated
"granisetron alone is worse" as a synergism claim and let Carlisle's "no
synergism in trials by other authors" refute it. That reading is defensible and
may well be better than gold's. The label was annotated as disputed and left
alone, because revising a label after seeing a prediction is scoring-to-fit.
Resolve it from Carlisle's full text.

**The precision number is not what it looks like.** claim_precision 0.400 comes
from the compiler emitting 15 propositions where gold has 6, splitting nausea
from vomiting and per-drug comparisons. That is arguably MORE faithful than
gold, since those are different outcomes with different effect sizes. Gold's
claim granularity is a free parameter, and scoring claim-to-claim punishes
defensible choices. This argues the benchmark should be scored on answers to
questions rather than on claim alignment. Recorded as a measurement-design
finding, not fixed.

**Compiler's own reported friction** (useful, and consistent with findings
already on file): no effect-size or strength field, so "supports but greatly
attenuated" had to go in `notes`; free-string argument roles mean nothing stops
a second compiler emitting `drug` where this one emitted `agent`. Both are
already-known deferred gaps, now independently hit by a different agent.

---

## Cycle 5 (2026-09-26): canonicalization, and the first end-to-end run

Two things happened in this cycle and the second corrects the first.

### Canonicalization built, and the measured 0.000 fixed

Root cause of cycle 4's F1 0.000 was partly a bug in the corpus, not in the
matchers. `P-SYNERGISM`'s surface form is a general claim ("combining antiemetic
agents produces synergistic prevention") while its arguments were a specific drug
pair. Carlisle's actual finding is general, so the encoding was simply wrong, and
the surface forms agreed while the encodings could not.

`compiler/canonicalize.py` plus `compiler/equivalences.json` normalise claims
using DECLARED equivalences rather than a similarity threshold. The reason is the
false-merge gate: a wrong merge traces to one named rule that can be deleted,
instead of to a number that has to be retuned. One rule was added, with a guard,
because without the guard it over-applied to plain drug-versus-drug comparisons.
`RELATED` is deliberately not a merge, which is where the instance-versus-general
decoy lands.

Result on the 7 hand-authored gold pairs: 7/7, F1 1.000, zero false merges.

### First end-to-end run, which corrects that result

A blind LLM extraction of the same paper became available (produced by a separate
session with no access to the gold labels). Scored through the reasoner:

| metric | value |
|---|---|
| claim recall | 1.000 (all 6 gold claims found) |
| answer accuracy | 0.833 (5/6) |
| raw claim precision | 0.333 (15 propositions for 6 gold claims) |
| granularity-adjusted precision | 1.000 |
| hallucination rate | **0.0000** |
| false survivals / false collapses | 0 / 0 |

**Finding 1, and it invalidates the canonicalization win above.** The F1 1.000
was flattered by an artefact: both hand-authored corpora happened to use the same
symbol ids, so normalisation only had to reconcile predicates. Against a blind
extraction that invented its own vocabulary, the canonicalizer relates NOTHING --
every comparison returns DIFFERENT, and the FINER_GRAINED bucket in
`eval/extraction_granularity.py` is empty for that reason. Cross-vocabulary
canonicalization is the real problem and it is unsolved. The scoreboard now
reports both numbers rather than the flattering one.

**Finding 2: the precision hit was a spec gap, not a compiler error.** All 15
extracted claims are grounded in the source text at 1.00, with zero spurious
claims. The compiler split by endpoint (nausea, vomiting, nausea-or-vomiting)
where gold folds them into one PONV claim. Raw precision therefore punished it for
being more faithful to the paper than gold is.

**Fix, targeted at the spec only.** `compiler/EXTRACTION_SPEC.md` rule 2a now
states that endpoints of one outcome family are one claim, with the reason tied to
the task: endpoints of a family are not independently retractable, and this task
asks whether support survives rather than how large the effect is.

**Not fixed, and deliberately.** The one wrong answer, `P-GRANI-ALONE-WORSE`
(gold UNRESOLVED, extraction REFUTED), is recorded as `disputed` in
`gold_queries.json` with the gold label left unchanged. The extraction read it as
a synergism claim and attached Carlisle's no-synergism null as refuting evidence,
which is defensible. Revising a label after seeing a system's prediction is
scoring-to-fit; it should be resolved from Carlisle's full text.

---

## Cycle 6 (2026-09-26): cross-vocabulary canonicalization

Cycle 5's measured failure was that claim matching across two independently
invented vocabularies scored 0.000. `compiler/align_symbols.py` adds the symbol
resolution stage that `kir-v0.1/STRESS_TEST.md` finding 12 argued must run before
any claim matching: deciding which entity a name denotes is a different question
from deciding whether two claims are the same, and the second cannot work without
the first.

Alignment is by normalised label plus declared families, never fuzzy similarity,
for the same reason the equivalence rules are declared: a wrong alignment must
trace to a deletable declaration rather than to a threshold.

**Result: 0/15 -> 6/15 extracted claims matched, with 3 endpoint collapse groups.**

Symbol alignment reached 11 of 14 extracted symbols. Three endpoint symbols
(postoperative nausea, vomiting, nausea-or-vomiting) collapse onto one PONV symbol
via a declared family, which is `EXTRACTION_SPEC.md` rule 2a applied at symbol
level.

**A deferred review point turned into a measured failure.** An earlier review said
argument roles are unregistered free strings and two compilers could name one role
differently. I deferred it as prophylactic. The first end-to-end run produced
exactly that: the extraction encoded granisetron-beats-droperidol with roles
`agent`/`comparator` where the reference used `better`/`worse`, so two identical
claims compared DIFFERENT on role naming alone. Fixed with declared per-relation
role synonyms. Only true synonyms are listed; aliasing roles that mean different
things would be a false merge wearing a rename.

**An underspecification in the reference corpus.**
`P-DROPERIDOL-INFERIOR` had no outcome role at all, asserting that granisetron
beats droperidol without saying at what. Carlisle's figures for that comparison
are nausea and vomiting, so the outcome is PONV. Adding it let the two endpoint
variants collapse correctly while keeping the rescue-antiemesis variant SEPARATE,
which simply dropping the outcome role would have wrongly merged.

**The 9 still-unmatched claims, all diagnosed, none spurious.**

| group | count | diagnosis |
|---|---|---|
| rescue-outcome claims | 3 | The reference corpus has one rescue claim; the extraction found three distinct ones (two comparative, one reduction). Gold UNDER-COVERS the paper here. |
| synergy claims | 5 | The extraction models synergy pairwise at drug level (agent, co_agent, outcome); the reference models it at class level (combination vs monotherapy). Genuine modelling divergence, neither wrong. |
| antagonism claim | 1 | The extraction promotes it to its own claim; the reference encodes it as refuting evidence. Restructuring. |

**Stopping the fixes here, deliberately.** The two changes made were legitimate: a
true synonym declaration, and a real underspecification. Closing the remaining 9
would mean remodelling gold until it matches the extraction, which is
scoring-to-fit. The class-versus-pairwise synergy divergence is a genuine open
question about correct granularity at the ARGUMENT level, the same question rule
2a settled for endpoints, and it should be decided from the source text rather
than from what improves the number.

---

## Cycle 7 (2026-09-26): corpus growth, which is the strongest success condition

The stated strongest condition is that as the corpus grows, accuracy holds
without schema complexity exploding: "if every 100 new papers requires 20 new
special-case fields, the representation is failing." That had zero evidence at
two chains in one domain, so a third chain was added in a DIFFERENT domain.

**Chain 3: Sato-group bisphosphonate trials, bone health and neurology.**
Iwamoto et al. 2011 (PMID 21456887) pooled 7 Japanese RCTs into three
drug-specific hip-fracture claims (etidronate RR 0.16, alendronate 0.29,
risedronate 0.24) and one class-level conclusion. Confirmed RETRACTED via
Statement of Retraction PMID 28376663. Independent ground truth from Bolland et
al. 2016, Neurology (PMID 27920281), whose load-bearing sentence is that the
reductions occurred "regardless of intervention (relative risk 0.22, 95% CI
0.15-0.31), that greatly exceed those reported in meta-analyses of other trials."
"Regardless of intervention" is what makes these one artefact rather than three
drug findings.

Depth 2 again, and structurally harder than the PONV chains: the pooling step is
a THREE-premise derivation where earlier chains had one and two.

**Prediction recorded before encoding: zero new schema fields. Result: zero new
SEMANTIC fields.** The single schema change was adding `notes` to `Context`,
which was the only object in the schema lacking one. That is documentation parity,
not a new capability, and it surfaced only because this corpus needed to record
why a population restriction is a genuine world-condition rather than provenance.

| | before cycle 7 | after |
|---|---|---|
| chains | 2 | 3 |
| domains | 1 (anaesthesia) | 2 (+ bone health / neurology) |
| gold claims | 10 | 14 |
| max derivation arity | 2 | 3 |
| epistemic macro-F1 | 1.0000 | 1.0000 |
| propagation precision / recall | 1.0000 / 1.0000 | 1.0000 / 1.0000 |
| false collapses / missed collapses | 0 / 0 | 0 / 0 |
| new semantic schema fields | - | **0** |

**The magnitude gap appeared again, independently.** Bolland's finding is about
effect SIZE ("greatly exceed"), which K-IR v0.3 cannot represent, exactly as
granisetron's "greatly reduced" could not be represented in cycle 1. Two
unrelated domains hitting the same wall is evidence the gap is systemic rather
than incidental, and it is now the best-earned candidate for the next schema
change.

**One judgement call worth stating.** Bolland's integrity analysis is attached as
REFUTING only the class-level claim, not the three drug-specific ones. Attaching
it to those would be circular: they rest on the very trials whose integrity is in
question, so their correct fate is loss of support, not refutation. The
corresponding Assertion uses stance `neutral_report`, because "the support is
worthless" is not "the claim is false" -- the same distinction the whole project
rests on.

---

## Cycle 6 (2026-09-26): the LLM baseline, and why its margin does not count

**The BLOCKED row was measurable after all.** The same tmux capability that
enabled blind extraction enabled the baseline: a fresh agent was given the
Carlisle abstract and the six claim statements with no K-IR, no evidence
structure and no gold labels, and asked for each claim's status after the Fujii
trials are discarded.

Scope note, because this is easy to overclaim: with a single-document corpus,
retrieval is trivially perfect, so this is the **RAG-equivalent upper bound**,
not a weak LLM-only strawman. A real LLM+RAG system over a large corpus must
first retrieve the right paper and can only do worse.

**Result as labelled.**

| system | accuracy | false survival | UNRESOLVED/REFUTED mixups |
|---|---|---|---|
| LLM with source in context | 4/6 = 0.667 | 0 | 1 |
| K-IR reasoner | 6/6 = 1.000 | 0 | 0 |

Margin +33.3 points against a >= 10 point target.

**Why that PASS was withdrawn.** One of the two LLM errors is
`P-GRANI-ALONE-WORSE`, the label already annotated as disputed in cycle 5. The
baseline answered REFUTED. The blind extractor, reasoning by a completely
different route (it encoded the claim as a synergism claim and let Carlisle's
no-synergism finding refute it), also answered REFUTED. Two independent agents
disagreeing with gold in the same direction is evidence about the label, not
about the agents.

Flipping that one label moves two claims at once, because K-IR becomes wrong
exactly where the LLM becomes right:

```
if P-GRANI-ALONE-WORSE is really REFUTED:  llm=0.833  kir=0.833  margin=+0.0
```

So the headline is not +33.3. It is "+33.3 or +0.0, depending on an unresolved
reading of one claim". The scorer now reports **NOT ROBUST** and refuses the
PASS whenever a disputed label can drag the margin under target. Banking the
favourable reading would have been the single most misleading thing this
project could do, since the whole pitch is that the system is trustworthy about
what is and is not established.

**The substantive question, unresolved.** Does "no synergism between antiemetics
in trials by other authors" refute "PONV is more likely when granisetron is
given alone"? Not obviously: absence of *synergism* concerns the interaction
term, while the Fujii claim is a large monotherapy penalty (RR 4.20), and a
combination can beat monotherapy additively with no synergism at all. Cutting
the other way, Carlisle also reports "some evidence of antagonism", which would
argue against a monotherapy penalty. The abstract does not settle it. Needs
Carlisle's full text, which is paywalled.

**The second LLM error was a defensible call, not a blunder.** It answered
UNRESOLVED for ramosetron, reasoning that granisetron gets an explicit post-Fujii
restatement (Kranke 2012) while ramosetron gets none, and the abstract never
says what the residual non-Fujii ramosetron trials show. Gold says SUPPORTED on
the strength of "greatly reduced" implying a surviving effect. Gold is probably
right, but the baseline's caution is reasonable and the margin rests on thin
wording.

**Standing conclusion.** The LLM+RAG row moves from BLOCKED to MEASURED BUT NOT
ESTABLISHED. Resolving it needs the disputed label settled from full text, and
then a corpus far larger than six claims, where each claim is not worth 16.7
points.

---

## Cycle 7 (2026-09-26): the disputed label was settled against my own result

**Resolved on the text, not on convenience.** Carlisle's abstract reads:

> "There was no synergism between antiemetics in trials by other authors.
> **In contrast**, in studies by Fujii et al., postoperative nausea and vomiting
> was more likely if granisetron was administered alone: nausea 4.20 (1.94-9.08)..."

The "in contrast" construction explicitly pairs the two sentences. Carlisle is
presenting the monotherapy penalty AS the Fujii-side counterpart of the
synergism question, so the non-Fujii no-synergism finding is evidence directly
against the claim rather than silent on it. "Some evidence of antagonism" cuts
the same way. `P-GRANI-ALONE-WORSE` is therefore INCONSISTENT before retraction
and REFUTED after.

**My gold was wrong. Both agents were right.** The blind extractor (cycle 5) and
the LLM baseline (cycle 6) independently answered REFUTED by different routes.
Two agents disagreeing with a hand label in the same direction was the signal
that prompted re-reading the source.

**Note which way the correction runs.** Flipping the label made the K-IR
reasoner wrong on that claim and erased the headline:

```
margin over LLM baseline: +0.0 pts   verdict: TIE/LOSS
```

It was changed because the text says so. It does not help, which is the point.

**A second, separate error: the corpus encoding.** The hand-built graph attached
only Fujii evidence to that claim and never attached Carlisle's no-synergism
finding as refuting it. That is a real modelling bug, and the blind LLM
extraction did not make it. Fixed by adding `EV-OTHER-NO-SYNERGISM`.

**Why the resulting +16.7 does not count either.** That fix was prompted by the
baseline's answers, so a margin re-measured on the same six claims is not an
independent comparison. Rather than leave that in prose where it can be
forgotten, the corpus now carries a `CONTAMINATION-MARKER` at the point of the
fix and the scorer detects it, refusing a clean verdict:

```
verdict: CONTAMINATED -- +16.7 pts, but measured after a baseline-prompted
         fix to the reference graph. Not independent.
```

**Standing conclusion, unchanged in substance.** The margin over an LLM with the
source in context is still NOT established. It has now been, in order: +33.3
(on a bad label), +0.0 (on the corrected label), and +16.7 (after fixing a bug
the baseline itself revealed). None of those is a result. Establishing one
requires claims neither system has seen.

**What this cycle actually demonstrated.** The baseline was more useful as an
error-finder than as a competitor: it located a wrong gold label and a wrong
encoding, both in the hand-built artefacts, neither in the reasoner.

---

## Cycle 8 (2026-09-26): the independent margin, and it is NEGATIVE

**Setup.** Eight claims across two chains in two domains (Sato/bisphosphonates,
Fujii/combination-review), neither carrying a contamination marker, neither seen
by the earlier baseline. `eval/baselines/unseen_eval.py` refuses to score any
graph that does carry a marker.

**The number moved four times. Every move is recorded because every move was a
correction to my own artefacts, not to the systems.**

| stage | margin | what was wrong |
|---|---|---|
| first unseen run | +25.0 | gold label the baseline correctly disputed |
| corrected that label | +12.5 | K-IR won on evidence the baseline never received |
| matched the evidence, re-ran | +12.5 | remaining win was a third bad gold label |
| corrected that label | **-12.5** | current honest figure |

**Final: LLM 8/8, K-IR 7/8, margin -12.5 points. The reasoner LOSES.**

**Error 1: integrity evidence is not counter-evidence.** The baseline answered
UNRESOLVED on the bisphosphonate class claim and argued that counting Bolland's
integrity analysis as refutation would "double-dip": it is grounds for
discarding the Sato series, not evidence that bisphosphonates fail. Correct, and
it contradicted the schema's own rule that retraction removes support rather
than manufacturing refutation. The corpus had a `stance: refutes` Evidence item
that should never have existed. Note this correction RAISED the baseline's score.

**Error 2: information asymmetry in my own experiment.** K-IR's one remaining
win was on a claim where its graph encodes Carlisle's no-synergism finding,
while Carlisle's abstract was not in the baseline's source file at all. A system
with strictly more evidence beating one with less is a broken experiment. Fixed
by adding Carlisle and re-running a fresh baseline.

**Error 3: inconsistent generality.** With Carlisle in hand the baseline marked
`P-TRAD-ADJUNCT-SUPERIOR` REFUTED while keeping `P-DEX-ENHANCES` UNRESOLVED,
because Carlisle's pool contains droperidol and metoclopramide (which the review
itself classifies as traditional antiemetics) but never dexamethasone. Verified
directly against the text. My gold had marked the GENERAL principle REFUTED on
that Carlisle sentence while marking the SPECIFIC instance Carlisle actually
tested UNRESOLVED, which is incoherent. Correcting it is what produced the
negative margin.

**What this cycle actually establishes.** The headline claim is not merely
unproven, it is currently false on the only independent measurement taken: an
LLM with the same sources matched the gold perfectly and the reasoner did not.
Three of the three disagreements across cycles 6 to 8 were resolved AGAINST the
hand-built artefacts. The baseline has been a better label auditor than its
author.

**What it does not establish.** The reasoner's loss is a single claim on n=8,
where each claim is 12.5 points. It is one missing Evidence edge in a
hand-encoded graph, not a demonstrated reasoning failure: the fixpoint does what
it should given its inputs. The honest reading is that the bottleneck is
COMPILATION and CURATION, not inference, which is consistent with cycle 5, where
the blind extraction beat the hand encoding on exactly this kind of edge.

**Deliberately NOT done.** Adding the missing Carlisle edge to
`P-TRAD-ADJUNCT-SUPERIOR` would take K-IR back to 8/8 and the margin to 0.0.
That fix is baseline-prompted, so doing it and re-reporting would repeat the
cycle-7 contamination. The edge is left missing and the loss stands until the
margin can be measured on claims nobody has iterated on.

---

## Cycle 9 (2026-09-26): canonicalization was never being measured

**The 0.000 was measuring the wrong thing.** Cross-vocabulary claim matching had
been reported as F1 0.000 since cycle 5, described as "the measured case for a
real canonicalization stage". But `compiler/canonicalize.py`, the declared-
equivalence canonicalizer, already existed and already resolved the gold pair
correctly. It was simply never listed in `eval/canonicalization_eval.py`'s
matcher table, so the eval was measuring the ABSENCE of a stage rather than the
stage itself, and reporting that absence as a capability gap.

Wiring it in:

```
matcher                  TP FP FN  prec   rec    F1     false_merge  gate
never_merge (current)    0  0  1   0.000  0.000  0.000  0.000        PASS
declared_equivalence     1  0  0   1.000  1.000  1.000  0.000        PASS
same_predicate           0  3  1   0.000  0.000  0.000  0.500        FAIL
lexical_overlap@0.5      0  1  1   0.000  0.000  0.000  0.167        FAIL
lexical_overlap@0.3      0  3  1   0.000  0.000  0.000  0.500        FAIL
```

**Why the 1.000 is not a result, stated in the tool's own output.** The gold set
contains exactly one SAME pair and the equivalence rule was authored with that
pair in view. What the number does show is discrimination rather than mere
recall: P-SYNERGISM, P-DEX-ENHANCES, P-TRAD-ADJUNCT-SUPERIOR and
P-MULTI-RECEPTOR-PRINCIPLE all normalise to the same canonical predicate
`COMBINATION_OUTPERFORMS`, giving three chances to false-merge, and it declined
all three because it compares full normal forms including arguments. The
same-predicate and lexical matchers took exactly those bait pairs. A real number
needs SAME pairs the rules were not written for.

**Lesson worth keeping.** This is the second time a reported failure turned out
to be in the measurement rather than the system: cycle 5 found the retraction
selector bug in the scorer, and this cycle found an entire stage missing from
the matcher table. Before trusting a bad number, check that the thing being
scored is the thing that exists.

**Unchanged.** The gating suite still FAILS on epistemic macro-F1 0.9238, and
the independent margin is still -12.5. Neither is touched by this cycle.
