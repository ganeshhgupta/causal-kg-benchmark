#!/usr/bin/env python3
"""Run every measurement and print the scoreboard. Exit nonzero on regression.

One command so the loop does not depend on whoever last remembered which
scripts to run:

    python eval/run_all.py

Each entry names the target, the script that measures it, and whether a
regression should fail the run. Entries marked advisory report a number without
gating, either because there is no threshold (end-to-end accuracy on a single
paper) or because the measurement is known partial (cross-vocabulary matching).

Deliberately NOT included: any LLM-based baseline. Those cost money to run, so
they stay an explicit opt-in rather than something a "run everything" script
silently bills someone for.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

# (label, argv, gating, extract) where extract pulls the headline from stdout.
CHECKS = [
    ("reasoner unit tests",
     [sys.executable, "reasoner/test_epistemic_query.py"], True,
     lambda o: "ALL PASS" if "ALL PASS" in o else "FAILURES"),

    ("gold retraction eval (3 chains, 2 domains)",
     [sys.executable, "eval/retraction_eval.py"], True,
     lambda o: " | ".join(re.findall(
         r"(epistemic macro-F1|propagation precision|propagation recall)\s+([\d.]+)",
         o.split("POOLED")[-1])[0][:0] or
         [f"{k} {v}" for k, v in re.findall(
             r"(epistemic macro-F1|propagation precision|propagation recall)\s+([\d.]+)",
             o.split("POOLED")[-1])])),

    ("proof validity",
     [sys.executable, "eval/proof_validity.py"], True,
     lambda o: " | ".join(f"{k} {v}" for k, v in re.findall(
         r"(proof-chain validity|hallucinated step rate)\s+([\d.]+)", o))),

    ("contradiction detection",
     [sys.executable, "eval/contradiction_eval.py"], True,
     lambda o: " | ".join(f"{k} {v}" for k, v in re.findall(
         r"(contradiction recall|false contradictions)\s+\S*\s*=?\s*([\d.]+)", o))),

    ("compiler-error sensitivity",
     [sys.executable, "eval/robustness_eval.py"], False,
     lambda o: ("only baseline survives intact"
                if "survived intact: ['baseline']" in o
                else "UNEXPECTED: " + (re.search(r"survived intact: (.*)", o)
                                       or [""])[0])),

    ("evidence lint (all corpora)",
     [sys.executable, "compiler/lint_evidence.py"] +
     [str(p.relative_to(ROOT)) for p in
      sorted((ROOT / "scientific-dependency" / "corpus").glob("*.json"))], True,
     lambda o: "clean" if o.count("clean") >= 3 else "findings present"),

    ("LLM baseline margin (NOT GATING)",
     [sys.executable, "eval/baselines/llm_baseline_eval.py"], False,
     lambda o: (re.search(r"verdict: (.*)", o) or ["", "n/a"])[1].strip()[:88]),

    ("canonicalization, shared vocabulary",
     [sys.executable, "eval/canonicalization_eval.py"], False,
     lambda o: (re.search(r"best F1 among gate-passing:\s+(.*)", o) or
                ["", "n/a"])[1].strip()),

    ("canonicalization, cross vocabulary (PARTIAL)",
     [sys.executable, "compiler/align_symbols.py"], False,
     lambda o: (re.search(r"matched to a reference claim: (\S+)", o) or
                ["", "n/a"])[1]),

    ("non-LLM baselines",
     [sys.executable, "eval/baselines/naive_baselines.py"], False,
     lambda o: (re.search(r"margin:\s+(\S+)", o) or ["", "n/a"])[1] +
               " over best non-LLM baseline"),

    ("schema validation, all graphs",
     [sys.executable, "-c", """
import json, jsonschema, glob, sys
s = json.load(open('kir-v0.3/kir-schema-v0.3.json', encoding='utf-8'))
v = jsonschema.Draft202012Validator(s)
bad = 0
for f in sorted(glob.glob('scientific-dependency/corpus/*.json') +
                glob.glob('scientific-dependency/fixtures/*.json')):
    n = len(list(v.iter_errors(json.load(open(f, encoding='utf-8')))))
    if n:
        bad += 1
        print('INVALID', f, n)
print('graphs validating cleanly' if not bad else f'{bad} invalid')
sys.exit(1 if bad else 0)
"""], True,
     lambda o: o.strip().splitlines()[-1] if o.strip() else "no output"),
]


def main():
    failures, rows = [], []
    for label, argv, gating, extract in CHECKS:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
        out = proc.stdout + proc.stderr
        try:
            headline = extract(out) or "(no headline)"
        except Exception as exc:  # noqa: BLE001 - report, never mask
            headline = f"(could not parse output: {exc})"
        ok = proc.returncode == 0
        rows.append((label, ok, gating, headline))
        if gating and not ok:
            failures.append((label, out))

    width = max(len(r[0]) for r in rows) + 2
    print(f"{'check':{width}} {'status':10} headline")
    print("-" * (width + 12 + 40))
    for label, ok, gating, headline in rows:
        status = ("PASS" if ok else "FAIL") + ("" if gating else " (adv)")
        print(f"{label:{width}} {status:10} {headline}")

    print()
    if failures:
        print(f"{len(failures)} gating check(s) FAILED\n")
        for label, out in failures:
            print(f"----- {label} -----")
            print(out[-1500:])
        return 1

    print("all gating checks pass")
    print()
    print("LLM BASELINE: measured once (cycle 6), answers cached in "
          "eval/baselines/llm/, so re-scoring is free. Result is NOT ROBUST: "
          "+33.3 pts as labelled, +0.0 pts if the disputed label "
          "P-GRANI-ALONE-WORSE goes the other way. No claim about beating an "
          "LLM is supported by this repo until that label is settled from full "
          "text and the corpus is larger than six claims.")
    print("PARTIAL: cross-vocabulary claim matching. See eval/LOOP_LOG.md cycle 6 "
          "for why the residual is left open rather than closed by remodelling "
          "gold to match the extraction.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
