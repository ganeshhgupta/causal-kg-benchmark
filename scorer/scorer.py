#!/usr/bin/env python3
"""
Causal-KG Benchmark scorer (v5; compatible with any gold set following the
propositions/variants/pairs/hyperedges schema, e.g. the physics benchmark
at repo root or ml-ai-dataset/benchmark).

Core guarantees:
- Canonicalization checks BOTH relation and predicted proposition target.
- False merges are split by failure category; pooled rate is never the sole gate.
- Manufactured contradictions are a first-class safety metric.
- Per-class logical_relation recall is computed for every class with gold
  support and headlined as MIN (catches total collapse in any one class,
  e.g. a system that never predicts CONTRADICTS) and MACRO (overall
  degradation) -- generalizes v4's single-purpose compatible_recall gate,
  which is retained in the report for continuity but no longer needed in
  the headline since it's now one entry in this per-class breakdown.
- Pair axes remain independent.
- Compression is computed from the ACTUAL predicted e-class unions.
- Hyperedges support both positive and future negative gold examples.

Prediction format:
{
  "variant_predictions": [
    {
      "variant_id": "V001a",
      "proposition_id": "K001",
      "logical_relation": "EQUAL"
    }
  ],
  "pair_predictions": [
    {
      "pair_id": "P01",
      "logical_relation": "COMPATIBLE",
      "schema_relation": "SAME",
      "context_relation": "DISJOINT",
      "direction_relation": "OPPOSITE"
    }
  ],
  "hyperedge_predictions": [
    {"hyperedge_id": "H01", "entailed": true}
  ]
}

For pair predictions whose gold direction_relation is N/A, omitting
direction_relation is accepted and normalized to N/A.
"""

import argparse
import json
from pathlib import Path
from collections import Counter, defaultdict

LOGICAL = {"EQUAL", "ENTAILS", "ENTAILED_BY", "CONTRADICTS", "COMPATIBLE", "UNRELATED"}
SCHEMA = {"SAME", "RELATED", "DIFFERENT"}
CONTEXT = {"SAME", "SUBSUMES", "SUBSUMED_BY", "OVERLAPS", "DISJOINT"}
DIRECTION = {"SAME", "OPPOSITE", "N/A"}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_list(obj, key):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and isinstance(obj.get(key), list):
        return obj[key]
    raise ValueError(f"{key}: expected top-level list or object containing {key!r}")


def safe_div(a, b):
    return a / b if b else 0.0


class DSU:
    def __init__(self, items):
        self.parent = {x: x for x in items}
        self.rank = {x: 0 for x in items}

    def find(self, x):
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        if a not in self.parent or b not in self.parent:
            return
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.rank[a] < self.rank[b]:
            a, b = b, a
        self.parent[b] = a
        if self.rank[a] == self.rank[b]:
            self.rank[a] += 1

    def class_count(self):
        return len({self.find(x) for x in self.parent})


def macro_f1(confusion, labels):
    per_label, f1s = {}, []
    for label in sorted(labels):
        tp = confusion[(label, label)]
        fp = sum(n for (g, p), n in confusion.items() if p == label and g != label)
        fn = sum(n for (g, p), n in confusion.items() if g == label and p != label)
        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        f1 = safe_div(2 * precision * recall, precision + recall)
        support = tp + fn
        per_label[label] = {
            "precision": precision, "recall": recall, "f1": f1, "support": support
        }
        if support:
            f1s.append(f1)
    return safe_div(sum(f1s), len(f1s)), per_label


def binary_metrics(tp, fp, fn, tn):
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    f1 = safe_div(2 * precision * recall, precision + recall)
    accuracy = safe_div(tp + tn, tp + fp + fn + tn)
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-dir", required=True)
    ap.add_argument("--predictions", required=True)
    ap.add_argument("--json-out")
    ap.add_argument("--allow-missing", action="store_true",
                    help="Development only: allow incomplete prediction files.")
    args = ap.parse_args()

    root = Path(args.gold_dir)
    propositions = pick_list(load_json(root / "propositions.json"), "propositions")
    variants = pick_list(load_json(root / "variants.json"), "variants")
    pairs = pick_list(load_json(root / "pairs.json"), "pairs")
    hyperedges = pick_list(load_json(root / "hyperedges.json"), "hyperedges")
    pred = load_json(args.predictions)

    prop_ids = {p["id"] for p in propositions}
    var_ids = {v["id"] for v in variants}
    pair_ids = {p["id"] for p in pairs}
    hyper_ids = {h["id"] for h in hyperedges}

    vp_list = pred.get("variant_predictions", [])
    pp_list = pred.get("pair_predictions", [])
    hp_list = pred.get("hyperedge_predictions", [])

    vp = {r["variant_id"]: r for r in vp_list}
    pp = {r["pair_id"]: r for r in pp_list}
    hp = {r["hyperedge_id"]: r for r in hp_list}

    # Basic format validation.
    if len(vp) != len(vp_list):
        raise SystemExit("Duplicate variant_id in predictions.")
    if len(pp) != len(pp_list):
        raise SystemExit("Duplicate pair_id in predictions.")
    if len(hp) != len(hp_list):
        raise SystemExit("Duplicate hyperedge_id in predictions.")

    unknown_variant_targets = sorted({
        r.get("proposition_id") for r in vp_list
        if r.get("proposition_id") is not None and r.get("proposition_id") not in prop_ids
    })
    if unknown_variant_targets:
        raise SystemExit(f"Unknown predicted proposition_id(s): {unknown_variant_targets}")

    missing_variants = sorted(var_ids - vp.keys())
    missing_pairs = sorted(pair_ids - pp.keys())
    missing_hyperedges = sorted(hyper_ids - hp.keys())

    if not args.allow_missing and (missing_variants or missing_pairs or missing_hyperedges):
        msg = ["Prediction file is incomplete."]
        if missing_variants:
            msg.append(f"missing variants={missing_variants}")
        if missing_pairs:
            msg.append(f"missing pairs={missing_pairs}")
        if missing_hyperedges:
            msg.append(f"missing hyperedges={missing_hyperedges}")
        raise SystemExit("\n".join(msg))

    # ------------------------------------------------------------------
    # 1) Variant canonicalization: target selection + relation correctness
    # ------------------------------------------------------------------
    ordinary = [v for v in variants if "deliberate_error" not in v]
    decoys = [v for v in variants if "deliberate_error" in v]

    correct_merges = []
    false_splits = []
    wrong_target_equals = []
    wrong_target_non_equals = []
    decoy_false_merges = []
    decoy_rejections = []
    target_correct = 0

    for v in variants:
        pr = vp.get(v["id"], {})
        pred_rel = pr.get("logical_relation")
        pred_target = pr.get("proposition_id")
        gold_target = v["proposition_id"]

        if pred_target == gold_target:
            target_correct += 1

        is_decoy = "deliberate_error" in v
        if is_decoy:
            if pred_rel == "EQUAL":
                # EQUAL to ANY canonical proposition is unsafe for a context-dropped
                # decoy. The target is recorded so the corruption is auditable.
                decoy_false_merges.append({
                    "variant_id": v["id"],
                    "predicted_target": pred_target,
                    "gold_parent": gold_target,
                })
            else:
                decoy_rejections.append(v["id"])
        else:
            if pred_rel == "EQUAL" and pred_target == gold_target:
                correct_merges.append(v["id"])
            elif pred_rel == "EQUAL" and pred_target != gold_target:
                # Critical hole fixed: "EQUAL" to wrong canonical proposition.
                wrong_target_equals.append({
                    "variant_id": v["id"],
                    "predicted_target": pred_target,
                    "gold_target": gold_target,
                })
            else:
                false_splits.append(v["id"])
                if pred_target != gold_target:
                    wrong_target_non_equals.append({
                        "variant_id": v["id"],
                        "predicted_target": pred_target,
                        "gold_target": gold_target,
                    })

    correct_merge_rate = safe_div(len(correct_merges), len(ordinary))
    false_split_rate = safe_div(len(false_splits), len(ordinary))
    decoy_false_merge_rate = safe_div(len(decoy_false_merges), len(decoys))
    decoy_rejection_rate = safe_div(len(decoy_rejections), len(decoys))
    wrong_target_equal_rate = safe_div(len(wrong_target_equals), len(ordinary))
    target_selection_accuracy = safe_div(target_correct, len(variants))

    # ------------------------------------------------------------------
    # 2) Cross-proposition false merges + manufactured contradictions
    # ------------------------------------------------------------------
    pair_false_merges = []
    pair_merge_negative_total = 0
    manufactured_contradictions = []
    contradiction_negative_total = 0

    for pair in pairs:
        gold = pair["logical_relation"]
        predicted = pp.get(pair["id"], {}).get("logical_relation")

        if gold != "EQUAL":
            pair_merge_negative_total += 1
            if predicted == "EQUAL":
                pair_false_merges.append(pair["id"])

        # Any gold relation other than CONTRADICTS says the benchmark does not
        # license an explicit contradiction for this pair.
        if gold != "CONTRADICTS":
            contradiction_negative_total += 1
            if predicted == "CONTRADICTS":
                manufactured_contradictions.append(pair["id"])

    pair_false_merge_rate = safe_div(len(pair_false_merges), pair_merge_negative_total)
    manufactured_contradiction_rate = safe_div(
        len(manufactured_contradictions), contradiction_negative_total
    )

    # Generalized per-class recall over logical_relation, replacing the v4
    # single-purpose "compatible_recall" gate. v4 added compatible_recall
    # because a conservative system could default every uncertain COMPATIBLE
    # pair to UNRELATED and still look perfect on every other headline gate.
    # The same hole exists for ANY class with real gold examples -- v5 found
    # this concretely for CONTRADICTS the moment a real gold CONTRADICTS pair
    # (the ml-ai BatchNorm pair) existed to test it with: predicting
    # COMPATIBLE for a gold CONTRADICTS pair triggered no existing gate.
    # Rather than keep adding one bespoke *_recall gate per class as new gold
    # classes appear, compute recall for every class that has gold support
    # and headline with the minimum (catches total collapse in ANY one
    # class) and the macro average (overall degradation, since min alone
    # can't distinguish "one class totally broken" from "barely below 100%").
    class_ids = defaultdict(list)
    class_correct = defaultdict(int)
    class_confusion_examples = defaultdict(list)
    for pair in pairs:
        gold = pair["logical_relation"]
        predicted = pp.get(pair["id"], {}).get("logical_relation")
        class_ids[gold].append(pair["id"])
        if predicted == gold:
            class_correct[gold] += 1
        else:
            class_confusion_examples[gold].append({"pair_id": pair["id"], "predicted": predicted})

    class_recalls = {
        cls: safe_div(class_correct[cls], len(ids))
        for cls, ids in class_ids.items()
    }
    supported_classes = sorted(class_recalls.keys())
    min_supported_class_recall = min(class_recalls.values()) if class_recalls else 1.0
    macro_supported_class_recall = safe_div(sum(class_recalls.values()), len(class_recalls)) if class_recalls else 1.0
    weakest_classes = sorted(
        [c for c in supported_classes if class_recalls[c] == min_supported_class_recall]
    )

    # Retained for continuity/back-compat with v4 reports.
    compatible_pairs = [p for p in pairs if p["logical_relation"] == "COMPATIBLE"]
    compatible_correct = class_correct.get("COMPATIBLE", 0)
    compatible_missed = [x["pair_id"] for x in class_confusion_examples.get("COMPATIBLE", [])]
    compatible_predicted_as_unrelated = [x["pair_id"] for x in class_confusion_examples.get("COMPATIBLE", []) if x["predicted"] == "UNRELATED"]
    compatible_predicted_as_contradicts = [x["pair_id"] for x in class_confusion_examples.get("COMPATIBLE", []) if x["predicted"] == "CONTRADICTS"]
    compatible_recall = class_recalls.get("COMPATIBLE", 1.0)

    # Pooled false merge is retained for continuity/reporting, but not used as
    # the sole safety gate.
    # Continuity metric: pool the two original merge-negative categories only
    # (context-drop decoys + non-EQUAL proposition pairs). Wrong-target EQUALs
    # are a distinct canonical-target failure and have their own gate.
    pooled_false_merge_num = len(decoy_false_merges) + len(pair_false_merges)
    pooled_false_merge_den = len(decoys) + pair_merge_negative_total
    pooled_false_merge_rate = safe_div(pooled_false_merge_num, pooled_false_merge_den)

    # ------------------------------------------------------------------
    # 3) Actual predicted e-class compression
    # ------------------------------------------------------------------
    all_nodes = sorted(prop_ids | var_ids)
    dsu = DSU(all_nodes)

    # IMPORTANT: union against the PREDICTED target, not the gold target.
    for v in variants:
        pr = vp.get(v["id"], {})
        if pr.get("logical_relation") == "EQUAL":
            target = pr.get("proposition_id")
            if target in prop_ids:
                dsu.union(v["id"], target)

    pair_by_id = {p["id"]: p for p in pairs}
    for pid, pr in pp.items():
        pair = pair_by_id.get(pid)
        if pair and pr.get("logical_relation") == "EQUAL":
            dsu.union(pair["a"], pair["b"])

    source_nodes = len(all_nodes)
    surviving_eclasses = dsu.class_count()
    compression_factor = safe_div(source_nodes, surviving_eclasses)
    compression_fraction = 1.0 - safe_div(surviving_eclasses, source_nodes)

    # ------------------------------------------------------------------
    # 4) Pair axes
    # ------------------------------------------------------------------
    axis_labels = {
        "logical_relation": LOGICAL,
        "schema_relation": SCHEMA,
        "context_relation": CONTEXT,
        "direction_relation": DIRECTION,
    }
    axis_results = {}

    for axis, labels in axis_labels.items():
        confusion = Counter()
        for pair in pairs:
            gold = pair.get(axis)
            predicted = pp.get(pair["id"], {}).get(axis)
            # Minor usability fix: omitted direction is equivalent to N/A only
            # when the gold says direction is not applicable.
            if axis == "direction_relation" and gold == "N/A" and predicted is None:
                predicted = "N/A"
            confusion[(gold, predicted)] += 1

        total = sum(confusion.values())
        correct = sum(n for (g, p), n in confusion.items() if g == p)
        mf1, per_label = macro_f1(confusion, labels)
        axis_results[axis] = {
            "total": total,
            "correct": correct,
            "accuracy": safe_div(correct, total),
            "macro_f1": mf1,
            "per_label": per_label,
            "confusion": {
                f"{g}->{p}": n
                for (g, p), n in sorted(confusion.items(), key=lambda kv: str(kv[0]))
            },
        }

    # ------------------------------------------------------------------
    # 5) Directional entailment preservation
    # ------------------------------------------------------------------
    epairs = [p for p in pairs if p["logical_relation"] in {"ENTAILS", "ENTAILED_BY"}]
    entail_correct = entail_to_equal = entail_to_unrelated = entail_reversed = 0

    for pair in epairs:
        pred_rel = pp.get(pair["id"], {}).get("logical_relation")
        gold_rel = pair["logical_relation"]
        entail_correct += pred_rel == gold_rel
        entail_to_equal += pred_rel == "EQUAL"
        entail_to_unrelated += pred_rel == "UNRELATED"
        entail_reversed += (
            (gold_rel == "ENTAILS" and pred_rel == "ENTAILED_BY") or
            (gold_rel == "ENTAILED_BY" and pred_rel == "ENTAILS")
        )

    entailment_accuracy = safe_div(entail_correct, len(epairs))

    # ------------------------------------------------------------------
    # 6) Hyperedges: positive AND future negative examples
    # ------------------------------------------------------------------
    # Gold convention:
    #   explicit "entailed": bool wins if present;
    #   otherwise relation == "ENTAILS" means positive (v0.2 compatibility).
    tp = fp = fn = tn = 0
    for h in hyperedges:
        gold_entailed = h.get("entailed")
        if gold_entailed is None:
            gold_entailed = h.get("relation") == "ENTAILS"
        pred_entailed = hp.get(h["id"], {}).get("entailed")
        if pred_entailed is True and gold_entailed is True:
            tp += 1
        elif pred_entailed is True and gold_entailed is False:
            fp += 1
        elif pred_entailed is False and gold_entailed is True:
            fn += 1
        elif pred_entailed is False and gold_entailed is False:
            tn += 1
        # Missing is already prevented unless --allow-missing.

    hyper_metrics = binary_metrics(tp, fp, fn, tn)

    # Data-coverage diagnostics: make unsupported relation classes obvious.
    pair_gold_support = Counter(p["logical_relation"] for p in pairs)
    hyper_gold_support = Counter(
        bool(h.get("entailed", h.get("relation") == "ENTAILS")) for h in hyperedges
    )
    dataset_warnings = []
    if pair_gold_support["CONTRADICTS"] == 0:
        dataset_warnings.append("No gold CONTRADICTS pair: contradiction recall is untested.")
    if pair_gold_support["EQUAL"] == 0:
        dataset_warnings.append("No cross-proposition gold EQUAL pair: cross-proposition equality recall is untested.")
    if hyper_gold_support[False] == 0:
        dataset_warnings.append("No negative hyperedge: hyperedge precision is untested.")
    if hyper_gold_support[True] == 0:
        dataset_warnings.append("No positive hyperedge: hyperedge recall is untested.")

    # ------------------------------------------------------------------
    # 7) Lexicographic summary
    # ------------------------------------------------------------------
    # Separate category gates prevent a perfect category from masking total
    # collapse in another category.
    lexicographic_key = (
        1.0 - decoy_false_merge_rate,
        1.0 - pair_false_merge_rate,
        1.0 - wrong_target_equal_rate,
        1.0 - manufactured_contradiction_rate,
        min_supported_class_recall,
        macro_supported_class_recall,
        correct_merge_rate,
        entailment_accuracy,
        compression_fraction,
    )

    report = {
        "canonicalization": {
            "ordinary_variants": len(ordinary),
            "decoys": len(decoys),
            "correct_merges": len(correct_merges),
            "correct_merge_rate": correct_merge_rate,
            "false_splits": len(false_splits),
            "false_split_rate": false_split_rate,
            "false_split_ids": false_splits,
            "target_selection_accuracy": target_selection_accuracy,
            "wrong_target_equals": wrong_target_equals,
            "wrong_target_equal_rate": wrong_target_equal_rate,
            "wrong_target_non_equals": wrong_target_non_equals,
        },
        "false_merge_safety": {
            "wrong_target_equals": wrong_target_equals,
            "wrong_target_equal_rate": wrong_target_equal_rate,
            "decoy_false_merges": decoy_false_merges,
            "decoy_false_merge_rate": decoy_false_merge_rate,
            "decoy_rejection_rate": decoy_rejection_rate,
            "pair_false_merge_ids": pair_false_merges,
            "pair_false_merge_rate": pair_false_merge_rate,
            "pooled_false_merge_count": pooled_false_merge_num,
            "pooled_false_merge_rate": pooled_false_merge_rate,
            "total_false_merge_count_all_categories": pooled_false_merge_num + len(wrong_target_equals),
        },
        "contradiction_safety": {
            "manufactured_contradiction_ids": manufactured_contradictions,
            "manufactured_contradiction_rate": manufactured_contradiction_rate,
        },
        "compatible_recognition": {
            "gold_compatible_total": len(compatible_pairs),
            "correct": compatible_correct,
            "recall": compatible_recall,
            "missed_ids": compatible_missed,
            "predicted_as_unrelated_ids": compatible_predicted_as_unrelated,
            "predicted_as_contradicts_ids": compatible_predicted_as_contradicts,
        },
        "class_recalls": {
            "per_class": {
                cls: {
                    "support": len(class_ids[cls]),
                    "correct": class_correct[cls],
                    "recall": class_recalls[cls],
                    "missed": class_confusion_examples[cls],
                }
                for cls in supported_classes
            },
            "min_supported_class_recall": min_supported_class_recall,
            "macro_supported_class_recall": macro_supported_class_recall,
            "weakest_classes": weakest_classes,
        },
        "compression": {
            "source_nodes": source_nodes,
            "surviving_eclasses": surviving_eclasses,
            "compression_factor": compression_factor,
            "compression_fraction": compression_fraction,
        },
        "pair_axes": axis_results,
        "directional_entailment": {
            "total": len(epairs),
            "correct": entail_correct,
            "accuracy": entailment_accuracy,
            "flattened_to_equal": entail_to_equal,
            "flattened_to_unrelated": entail_to_unrelated,
            "direction_reversed": entail_reversed,
        },
        "hyperedges": hyper_metrics,
        "dataset_support": {
            "pair_logical_relation_support": dict(pair_gold_support),
            "hyperedge_gold_support": {
                "entailed_true": hyper_gold_support[True],
                "entailed_false": hyper_gold_support[False],
            },
            "warnings": dataset_warnings,
        },
        "coverage": {
            "missing_variant_predictions": missing_variants,
            "missing_pair_predictions": missing_pairs,
            "missing_hyperedge_predictions": missing_hyperedges,
        },
        "lexicographic_key": list(lexicographic_key),
        "lexicographic_definition": [
            "1-decoy_false_merge_rate",
            "1-pair_false_merge_rate",
            "1-wrong_target_equal_rate",
            "1-manufactured_contradiction_rate",
            "min_supported_class_recall",
            "macro_supported_class_recall",
            "correct_merge_rate",
            "directional_entailment_accuracy",
            "compression_fraction",
        ],
    }

    print("\n=== Causal-KG Benchmark ===\n")
    print("1) Canonicalization")
    print(f"   Correct-merge rate          {correct_merge_rate:.3%} ({len(correct_merges)}/{len(ordinary)})")
    print(f"   False-split rate            {false_split_rate:.3%} ({len(false_splits)}/{len(ordinary)})")
    print(f"   Target-selection accuracy   {target_selection_accuracy:.3%} ({target_correct}/{len(variants)})")
    print(f"   Wrong-target EQUAL rate     {wrong_target_equal_rate:.3%} ({len(wrong_target_equals)}/{len(ordinary)})")

    print("\n2) False-merge safety (NEVER rely on pooled alone)")
    print(f"   Wrong-target EQUAL rate     {wrong_target_equal_rate:.3%} ({len(wrong_target_equals)}/{len(ordinary)})")
    print(f"   Decoy false-merge rate      {decoy_false_merge_rate:.3%} ({len(decoy_false_merges)}/{len(decoys)})")
    print(f"   Pair false-merge rate       {pair_false_merge_rate:.3%} ({len(pair_false_merges)}/{pair_merge_negative_total})")
    print(f"   Pooled false-merge rate     {pooled_false_merge_rate:.3%} ({pooled_false_merge_num}/{pooled_false_merge_den})")

    print("\n3) Contradiction safety")
    print(f"   Manufactured contradictions {manufactured_contradiction_rate:.3%} ({len(manufactured_contradictions)}/{contradiction_negative_total})")

    print("\n4) Per-class logical_relation recall (min/macro over gold-supported classes)")
    for cls in supported_classes:
        print(f"   {cls:12s} recall={class_recalls[cls]:.3%}  (support={len(class_ids[cls])})")
    print(f"   MIN recall (headline)        {min_supported_class_recall:.3%}  weakest={weakest_classes}")
    print(f"   MACRO recall (headline)      {macro_supported_class_recall:.3%}")

    print("\n5) Predicted e-class compression")
    print(f"   Source nodes                {source_nodes}")
    print(f"   Surviving e-classes         {surviving_eclasses}")
    print(f"   Compression factor          {compression_factor:.3f}x")
    print(f"   Reduction fraction          {compression_fraction:.3%}")

    print("\n6) Pair axes")
    for axis in ("logical_relation", "schema_relation", "context_relation", "direction_relation"):
        r = axis_results[axis]
        print(f"   {axis:22s} acc={r['accuracy']:.3%}  macro-F1={r['macro_f1']:.3%}")

    print("\n7) Directional entailment")
    print(f"   Accuracy                    {entailment_accuracy:.3%} ({entail_correct}/{len(epairs)})")
    print(f"   Flattened -> EQUAL          {entail_to_equal}")
    print(f"   Flattened -> UNRELATED      {entail_to_unrelated}")
    print(f"   Direction reversed          {entail_reversed}")

    print("\n8) Hyperedges")
    print(f"   Accuracy                    {hyper_metrics['accuracy']:.3%}")
    print(f"   Precision                   {hyper_metrics['precision']:.3%}")
    print(f"   Recall                      {hyper_metrics['recall']:.3%}")
    print(f"   F1                          {hyper_metrics['f1']:.3%}")

    print("\nLexicographic key (higher is better):")
    print("   ", report["lexicographic_definition"])
    print("   ", tuple(round(x, 6) for x in lexicographic_key))

    if wrong_target_equals:
        print("\nCRITICAL wrong-target EQUAL merges:")
        for x in wrong_target_equals:
            print(f"   {x['variant_id']}: predicted {x['predicted_target']}, gold {x['gold_target']}")
    if decoy_false_merges:
        print("\nCRITICAL decoy false merges:")
        for x in decoy_false_merges:
            print(f"   {x['variant_id']} -> {x['predicted_target']}")
    if pair_false_merges:
        print("\nCRITICAL cross-proposition false merges:", ", ".join(pair_false_merges))
    if manufactured_contradictions:
        print("\nCRITICAL manufactured contradictions:", ", ".join(manufactured_contradictions))
    if compatible_missed:
        print("\nCRITICAL missed COMPATIBLE pairs:", ", ".join(compatible_missed))
    if min_supported_class_recall < 1.0:
        print(f"\nCRITICAL weakest logical_relation class(es) {weakest_classes} at {min_supported_class_recall:.3%} recall:")
        for cls in weakest_classes:
            for miss in class_confusion_examples[cls]:
                print(f"   {miss['pair_id']}: gold={cls}, predicted={miss['predicted']}")

    if dataset_warnings:
        print("\nDataset coverage warnings:")
        for w in dataset_warnings:
            print("  -", w)

    if missing_variants or missing_pairs or missing_hyperedges:
        print("\nCoverage warnings (--allow-missing):")
        if missing_variants:
            print("   variants:", ", ".join(missing_variants))
        if missing_pairs:
            print("   pairs:", ", ".join(missing_pairs))
        if missing_hyperedges:
            print("   hyperedges:", ", ".join(missing_hyperedges))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\nWrote {args.json_out}")


if __name__ == "__main__":
    main()
