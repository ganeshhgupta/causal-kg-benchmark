# ML/AI Papers Dataset (500 entries)

500 atomic technical/causal claims drawn primarily from well-known ML/AI
research papers, extending this repo's canonicalization-benchmark work from
the physics domain (`../propositions.json` etc.) into a much larger,
paper-sourced domain.

## Schema

Lighter-weight than the physics `propositions.json` (no formal
`context`/`MONOTONIC_*` apparatus) -- this is a paper-claim extraction
dataset, not a fully formalized K-IR benchmark:

```json
{"id": "M001", "domain": "transformers", "paper": "Vaswani et al. 2017 (Attention Is All You Need)", "claim": "..."}
```

- `id` -- M001-M500, unique
- `domain` -- one of 25 categories (20 entries each, see below)
- `paper` -- best-known original paper/authors for the claim; several
  claims are standard practice rather than tied to one paper, marked
  `"General ..."` accordingly rather than attributed to a paper that
  didn't originate them
- `claim` -- one atomic technical or causal statement, phrased to stand
  on its own

## Categories (25 x 20 = 500)

```
transformers              optimization              regularization
cnn_architectures          sequence_models            word_embeddings
gans                       vae_diffusion              rl_fundamentals
rl_advanced_alignment      scaling_laws               peft
model_compression          vision_transformers_detection
contrastive_ssl            graph_neural_networks      init_normalization
loss_metrics               mixture_of_experts         nas_automl
federated_distributed      explainability             retrieval_memory
generalization_theory      emerging_llm_techniques
```

## Status

Built in 5 batches of 100, each validated for unique IDs and complete
fields before committing. Claims are restricted to well-established,
high-confidence technical facts about widely-cited papers/methods
(architectures, training techniques, theory) rather than uncertain
numeric specifics (exact hyperparameter values, benchmark scores) that
would need direct paper verification to state safely.

## Known limitations / not yet done

- **Not independently fact-checked against the original papers.** Claims
  were generated from confident, well-established ML/AI knowledge, but
  unlike the physics benchmark's multi-round adversarial review, this
  batch has not yet been checked entry-by-entry against source papers or
  had a canonicalization/variants/pairs layer built on top of it.
- No paraphrase variants, decoys, or cross-claim relation pairs yet --
  this is the raw claim set only. If this feeds into the same
  canonicalization-benchmark methodology as the physics dataset, that
  layer (variants.json, pairs.json, hyperedges.json equivalents) is the
  natural next step, sourced from real paper text rather than
  hand-authored paraphrases.
- Some `domain` categories overlap conceptually (e.g. a Transformer
  claim could also touch `scaling_laws` or `peft`); each entry was
  assigned to its most central category, not necessarily the only
  relevant one.
