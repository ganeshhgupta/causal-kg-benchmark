import json, copy
from pathlib import Path

root = Path(__file__).parent
props = json.load(open(root / "propositions.json", encoding="utf-8"))["propositions"]
variants = json.load(open(root / "variants.json", encoding="utf-8"))["variants"]
pairs = json.load(open(root / "pairs.json", encoding="utf-8"))["pairs"]
hyperedges = json.load(open(root / "hyperedges.json", encoding="utf-8"))["hyperedges"]

def build_perfect():
    vp = []
    for v in variants:
        is_decoy = "deliberate_error" in v
        vp.append({
            "variant_id": v["id"],
            "proposition_id": v["proposition_id"],
            "logical_relation": "ENTAILED_BY" if is_decoy else "EQUAL",
        })
    pp = []
    for p in pairs:
        pp.append({
            "pair_id": p["id"],
            "logical_relation": p["logical_relation"],
            "schema_relation": p["schema_relation"],
            "context_relation": p["context_relation"],
            "direction_relation": p["direction_relation"],
        })
    hp = [{"hyperedge_id": h["id"], "entailed": True} for h in hyperedges]
    return {"variant_predictions": vp, "pair_predictions": pp, "hyperedge_predictions": hp}

perfect = build_perfect()
json.dump(perfect, open(root / "predictions.perfect.json", "w", encoding="utf-8"), indent=2)

# Adversarial probe: miss the one real contradiction (predict COMPATIBLE instead of CONTRADICTS for P05)
missed_contradiction = copy.deepcopy(perfect)
for row in missed_contradiction["pair_predictions"]:
    if row["pair_id"] == "P05":
        row["logical_relation"] = "COMPATIBLE"
json.dump(missed_contradiction, open(root / "predictions.missed_contradiction.json", "w", encoding="utf-8"), indent=2)

# Adversarial probe: manufacture a false contradiction on the flagship dropout phase pair (P03)
manufactured = copy.deepcopy(perfect)
for row in manufactured["pair_predictions"]:
    if row["pair_id"] == "P03":
        row["logical_relation"] = "CONTRADICTS"
json.dump(manufactured, open(root / "predictions.manufactured_contradiction.json", "w", encoding="utf-8"), indent=2)

# Adversarial probe: wrong-target false merge (V-M041b, the "dropout always on" decoy, wrongly EQUAL to M042 instead of correctly rejected)
wrong_target = copy.deepcopy(perfect)
for row in wrong_target["variant_predictions"]:
    if row["variant_id"] == "V-M041b":
        row["proposition_id"] = "M042"
        row["logical_relation"] = "EQUAL"
json.dump(wrong_target, open(root / "predictions.wrong_target.json", "w", encoding="utf-8"), indent=2)

print("wrote predictions.perfect.json, predictions.missed_contradiction.json, predictions.manufactured_contradiction.json, predictions.wrong_target.json")
