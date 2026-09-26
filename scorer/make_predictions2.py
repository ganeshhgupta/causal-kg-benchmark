import json, copy
from pathlib import Path

root = Path(__file__).parent.parent
pairs = json.load(open(root / "pairs.json", encoding="utf-8"))["pairs"]
base = json.load(open(Path(__file__).parent / "predictions.perfect.json", encoding="utf-8"))

# Probe A: flood every COMPATIBLE gold pair with UNRELATED instead.
probe_a = copy.deepcopy(base)
compatible_ids = {p["id"] for p in pairs if p["logical_relation"] == "COMPATIBLE"}
for row in probe_a["pair_predictions"]:
    if row["pair_id"] in compatible_ids:
        row["logical_relation"] = "UNRELATED"
json.dump(probe_a, open(Path(__file__).parent / "predictions.probeA_unrelated_flood.json", "w", encoding="utf-8"), indent=2)
print("COMPATIBLE gold pairs flooded with UNRELATED:", sorted(compatible_ids))

# Probe B: omit proposition_id entirely while still claiming EQUAL, for one variant.
probe_b = copy.deepcopy(base)
for row in probe_b["variant_predictions"]:
    if row["variant_id"] == "V001a":
        row.pop("proposition_id", None)
        row["logical_relation"] = "EQUAL"
json.dump(probe_b, open(Path(__file__).parent / "predictions.probeB_missing_target.json", "w", encoding="utf-8"), indent=2)
print("wrote probe B (V001a EQUAL with no proposition_id)")
