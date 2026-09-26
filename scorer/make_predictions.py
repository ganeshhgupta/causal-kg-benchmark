import json, sys
from pathlib import Path

root = Path(__file__).parent.parent
props = json.load(open(root / "propositions.json", encoding="utf-8"))["propositions"]
variants = json.load(open(root / "variants.json", encoding="utf-8"))["variants"]
pairs = json.load(open(root / "pairs.json", encoding="utf-8"))["pairs"]
hyperedges = json.load(open(root / "hyperedges.json", encoding="utf-8"))["hyperedges"]

mode = sys.argv[1] if len(sys.argv) > 1 else "perfect"

variant_predictions = []
for v in variants:
    is_decoy = "deliberate_error" in v
    rel = "ENTAILED_BY" if is_decoy else "EQUAL"
    variant_predictions.append({"variant_id": v["id"], "proposition_id": v["proposition_id"], "logical_relation": rel})

if mode == "wrong_proposition_id":
    # V004ca ("Copper expands when heated") correctly judged EQUAL, but assigned to
    # the WRONG proposition (K004m, the general metal law, instead of K004c).
    for vp in variant_predictions:
        if vp["variant_id"] == "V004ca":
            vp["proposition_id"] = "K004m"
            vp["logical_relation"] = "EQUAL"

pair_predictions = []
for p in pairs:
    entry = {
        "pair_id": p["id"],
        "logical_relation": p["logical_relation"],
        "schema_relation": p["schema_relation"],
        "context_relation": p["context_relation"],
        "direction_relation": p["direction_relation"],
    }
    pair_predictions.append(entry)

if mode == "manufactured_contradiction":
    for pe in pair_predictions:
        if pe["pair_id"] in ("P01", "P05"):
            pe["logical_relation"] = "CONTRADICTS"

hyperedge_predictions = [{"hyperedge_id": h["id"], "entailed": True} for h in hyperedges]

out = {
    "variant_predictions": variant_predictions,
    "pair_predictions": pair_predictions,
    "hyperedge_predictions": hyperedge_predictions,
}
json.dump(out, open(Path(__file__).parent / f"predictions.{mode}.json", "w", encoding="utf-8"), indent=2)
print(f"wrote predictions.{mode}.json")
