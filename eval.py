"""
eval.py
Runs all sample claims through the agent headlessly and compares the
resulting decision against the expected decision stored in
data/sample_claims.json (_expected_decision_for_eval). Prints a pass/fail
summary and writes full results to sample_outputs/eval_results.json.

Run with: python eval.py
"""
import json
import os
import sys
from dotenv import load_dotenv
import time

load_dotenv()

from agent import run_agent 

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "outputs")


def main():
    with open(os.path.join(DATA_DIR, "sample_claims.json")) as f:
        claims = json.load(f)

    os.makedirs(OUT_DIR, exist_ok=True)
    results = []
    passed, failed = 0, 0

    print(f"Running {len(claims)} sample claims through the agent...\n")

    for claim in claims:

        expected = claim.pop("_expected_decision_for_eval", None)
        claim.pop("_note", None)

        outcome = run_agent(claim)
        time.sleep(1)  # slight delay to avoid overwhelming the API or ratelimits
        decision = outcome["final_decision"]
        actual = decision.get("decision")

        ok = (actual == expected) if expected else None
        if ok:
            passed += 1
            status = "PASS"
        elif ok is False:
            failed += 1
            status = "FAIL"
        else:
            status = "N/A"

        print(f"[{status}] {claim['claim_id']}: expected={expected!r} actual={actual!r} "
              f"confidence={decision.get('confidence')} reasons={decision.get('reason_codes')}")

        results.append({
            "claim_id": claim["claim_id"],
            "expected_decision": expected,
            "actual_decision": actual,
            "status": status,
            "final_decision": decision,
            "audit_trail": outcome["audit_trail"],
        })

    out_path = os.path.join(OUT_DIR, "eval_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{passed} passed, {failed} failed, out of {len(claims)} total.")
    print(f"Full results written to {out_path}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
