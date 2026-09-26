# Extraction spec: paper text to K-IR v0.3

The contract handed to the compiler (an LLM) for each paper. Kept as a file so a
loop cycle is reproducible and so changes to the instructions are diffable, since
"we changed the prompt" is otherwise an invisible confound when scores move.

## Input

- one paper's text (abstract or full text)
- `kir-v0.3/kir-schema-v0.3.json`

## Output

A single JSON object validating against the schema, containing `symbols`,
`contexts`, `propositions`, `assertions`, `evidence`.

## Rules

1. **Extract object-level claims, not claims about the paper.** "Granisetron
   reduces PONV" is a proposition. "Carlisle analysed 168 trials" is not.

2. **One proposition per distinct claim.** Do not merge two claims that differ in
   agent, outcome, comparator or regimen. Do not split one claim across several
   propositions.

2a. **Granularity: endpoints of one outcome family are ONE claim.** Where a paper
   reports the same intervention against the same comparator on several related
   endpoints (nausea, vomiting, nausea-or-vomiting; or 30-day and 90-day
   mortality), that is one proposition over the outcome family, not one per
   endpoint. Two reasons, both task-specific rather than aesthetic: endpoints of
   one family are not independently retractable, since the same trials support
   all of them, and this task asks whether support survives rather than how large
   the effect is. Split only when the endpoints could come apart evidentially,
   for example if different trials measured them.

   Added after the first blind extraction produced 15 propositions for 6 gold
   claims. Every one was grounded in the source with zero hallucination, so this
   was never a compiler error: the spec simply had not said which granularity it
   wanted, and raw precision punished the compiler for being more faithful to the
   paper than gold was. If the coarser choice ever loses information the task
   needs, this rule is what should change, not the labels.

3. **A claim is one object however many sources bear on it.** If two groups
   studied the same claim and disagreed, that is ONE proposition with two
   `evidence` entries of opposite `stance`, never two propositions.

4. **Never put truth, confidence or source inside a proposition.** Those belong in
   `assertions` (who claimed it) and `evidence` (what bears on it).

5. **Evidence `stance` is `supports` or `refutes` relative to the proposition as
   written.** A specific null result against a claimed difference REFUTES that
   difference claim. A null result about some other comparison is not evidence
   either way and must be omitted.

6. **Group non-independent evidence.** Evidence sharing an author, cohort or
   dataset gets a shared `independence_group`. This is what makes "retract
   everything from this source" expressible.

7. **Set `status` to `active` for all evidence.** Retraction is applied by the
   query, not baked into the graph. A graph that pre-bakes the retraction cannot
   be asked what changed.

8. **Encode the claim as the original authors asserted it**, even where the paper
   is arguing it is an artefact. The epistemic layer decides what survives; the
   compiler's job is faithful representation, not judgement.

9. **Put every claim's source sentence in `surface_forms`.** Traceability.

10. **Do not invent a claim the text does not make**, and do not omit one it does.

## What is deliberately not specified

No list of predicates, no list of context keys, no target number of claims. Those
are what the loop is measuring. If the compiler invents a predicate per claim,
that shows up as a canonicalization failure rather than being prevented by fiat.
