# Loop log

One entry per cycle of `real papers -> extract/compile -> reason -> compare with
gold -> fix ONLY the failure`. The point of the log is that a fix is only
legitimate if a measured failure preceded it, so each entry names the failure
first and the change second.

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
