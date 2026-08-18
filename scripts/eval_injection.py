#!/usr/bin/env python3
"""Measure prompt-injection detection against two labelled corpora.

Run:  uv run --all-extras python scripts/eval_injection.py [--verbose]

Scores every case through the real scorer with behavioral=None -- the same
pinned-baseline path `{"deterministic": true}` uses -- so results are
reproducible and depend on nothing but the detectors.

The governing metric is the FALSE-POSITIVE RATE on benign traffic, not
detector count. A missed injection costs one sub-cent call. A false DENY on a
legitimate payment breaks the caller's router, which is the error they cannot
absorb. So two benign rates are tracked separately:

    FPR (soft)  benign scored anything other than APPROVE -- costs a STEP_UP
    FPR (hard)  benign scored DENY -- breaks the payment

and two detection rates:

    recall      injection scored anything other than APPROVE -- caught at all
    DENY rate   injection scored DENY -- blocked outright
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from circle.risk_scorer import evaluate_risk  # noqa: E402

CORPORA = pathlib.Path(__file__).resolve().parent.parent / "tests" / "corpora"
PAYEE = "blockrun.ai/openai/gpt-5.6-luna"      # legitimate, allowlisted payee
AMOUNT = "0.005"                                # their median call
SERVICE = "llm-inference"


def load(name: str) -> list[dict]:
    path = CORPORA / name
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def score(reason: str) -> tuple[str, int, list[str], float]:
    t0 = time.perf_counter()
    r = evaluate_risk(payee=PAYEE, amount=AMOUNT, service=SERVICE, reason=reason,
                      source_wallet="0x0000000000000000000000000000000000000001",
                      chain="BASE", behavioral=None)
    return r.decision, r.score, r.signals, (time.perf_counter() - t0) * 1000


def main() -> int:
    verbose = "--verbose" in sys.argv
    benign, attacks = load("benign.jsonl"), load("injection.jsonl")

    rows, timings = [], []
    for case, label in [(c, "benign") for c in benign] + [(c, "injection") for c in attacks]:
        decision, sc, signals, ms = score(case["reason"])
        timings.append(ms)
        rows.append({**case, "label": label, "decision": decision,
                     "score": sc, "signals": signals})

    b = [r for r in rows if r["label"] == "benign"]
    a = [r for r in rows if r["label"] == "injection"]

    fp_soft = [r for r in b if r["decision"] != "APPROVE"]
    fp_hard = [r for r in b if r["decision"] == "DENY"]
    caught = [r for r in a if r["decision"] != "APPROVE"]
    denied = [r for r in a if r["decision"] == "DENY"]
    missed = [r for r in a if r["decision"] == "APPROVE"]

    flagged = len(caught) + len(fp_soft)
    precision = len(caught) / flagged if flagged else 0.0

    print("═" * 66)
    print(f"  BENIGN   n={len(b):<3}  FPR soft {len(fp_soft)/len(b):6.1%} ({len(fp_soft)})"
          f"   FPR hard {len(fp_hard)/len(b):6.1%} ({len(fp_hard)})")
    print(f"  ATTACK   n={len(a):<3}  recall   {len(caught)/len(a):6.1%} ({len(caught)})"
          f"   DENY     {len(denied)/len(a):6.1%} ({len(denied)})")
    print(f"  precision {precision:.1%}   |   scorer p50 "
          f"{sorted(timings)[len(timings)//2]:.2f}ms")
    print("═" * 66)

    if fp_soft:
        print(f"\nFALSE POSITIVES on benign ({len(fp_soft)}) — each one costs the caller:")
        for r in fp_soft:
            print(f"  {r['id']} {r['decision']:8} {r['score']:>3}  [{r['tag']}] "
                  f"{','.join(r['signals'])}")
            print(f"        {r['reason'][:74]!r}")

    if missed:
        print(f"\nMISSED injections ({len(missed)}) — scored APPROVE:")
        for r in missed:
            print(f"  {r['id']} [{r['tag']:22}] {r['reason'][:64]!r}")

    if verbose:
        print("\nper-tag recall:")
        tags: dict[str, list] = {}
        for r in a:
            tags.setdefault(r["tag"], []).append(r["decision"] != "APPROVE")
        for tag, hits in sorted(tags.items()):
            print(f"  {tag:22} {sum(hits)}/{len(hits)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
