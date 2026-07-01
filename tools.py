"""
tools.py
Deterministic, non-LLM tool functions the agent can call.
Keeping these as plain Python (not LLM calls) is the point: the LLM decides
*when* to use them and how to combine results, but the checks themselves
are reliable and auditable rule logic, not generated text.
"""
import json
import os
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_json(filename):
    with open(os.path.join(DATA_DIR, filename), "r") as f:
        return json.load(f)


def load_policy_text():
    with open(os.path.join(DATA_DIR, "travel_policy.md"), "r") as f:
        return f.read()


LIMITS = _load_json("limits.json")
PROCESSED_LOG = _load_json("processed_claims_log.json")


def policy_lookup(topics: str) -> dict:
    """
    Tool 1: Policy lookup.
    Accepts a comma-separated string of topic keywords and returns all
    matching policy sections for each in one call.
    e.g. topics = "meals, alcohol, receipts, approval thresholds"
    """
    text = load_policy_text()
    sections = text.split("\n## ")

    topic_list = [t.strip().lower() for t in topics.split(",") if t.strip()]
    results = {}
    unmatched = []

    for topic in topic_list:
        matches = []
        for sec in sections:
            if topic in sec.lower():
                matches.append("## " + sec if not sec.startswith("#") else sec)
        if matches:
            results[topic] = matches
        else:
            unmatched.append(topic)

    available_headers = [s.split("\n")[0] for s in sections if s.strip()]

    return {
        "matched": results,
        "unmatched_topics": unmatched,
        "available_section_headers": available_headers if unmatched else [],
    }


def get_city_tier(city: str) -> dict:
    """Resolve a city to its tier and caps."""
    for tier_name, tier_data in LIMITS["city_tiers"].items():
        if tier_name == "tier_3":
            continue
        if city.strip().lower() in [c.lower() for c in tier_data["cities"]]:
            return {"tier": tier_name, **tier_data}
    return {"tier": "tier_3", **LIMITS["city_tiers"]["tier_3"]}


def limit_and_perdiem_check(destination_city: str, expense_lines: list) -> dict:
    """
    Tool 2: Per-diem / limit checker.
    Checks each expense line against city-tier caps (lodging/night, meals/day,
    misc/day) and flags ineligible categories. Returns per-line verdicts and
    a running total of approved vs deducted amounts.
    """
    tier_info = get_city_tier(destination_city)
    results = []
    total_claimed = 0.0
    total_approved = 0.0
    total_deducted = 0.0

    daily_totals = {}  # (date, category_group) -> running sum, for per-day caps

    for line in expense_lines:
        cat = line["category"].lower()
        amt = float(line["amount"])
        date = line.get("date")
        total_claimed += amt
        verdict = {
            "category": cat,
            "date": date,
            "vendor": line.get("vendor"),
            "claimed_amount": amt,
        }

        if cat in LIMITS["ineligible_categories"]:
            verdict["status"] = "ineligible_category"
            verdict["approved_amount"] = 0.0
            verdict["deducted_amount"] = amt
            verdict["reason"] = f"Category '{cat}' is not reimbursable per policy."
        elif cat == "lodging":
            cap = tier_info["lodging_cap_per_night"]
            approved = min(amt, cap)
            verdict["status"] = "ok" if amt <= cap else "over_cap"
            verdict["cap_applied"] = cap
            verdict["approved_amount"] = approved
            verdict["deducted_amount"] = round(amt - approved, 2)
            verdict["reason"] = (
                "Within lodging cap." if amt <= cap
                else f"Exceeds {tier_info['tier']} lodging cap of ${cap}/night; excess deducted."
            )
        elif cat == "meals":
            cap = tier_info["meal_cap_per_day"]
            key = (date, "meals")
            running = daily_totals.get(key, 0.0)
            remaining_cap = max(cap - running, 0)
            approved = min(amt, remaining_cap)
            daily_totals[key] = running + approved
            verdict["status"] = "ok" if amt <= remaining_cap else "over_cap"
            verdict["cap_applied"] = cap
            verdict["approved_amount"] = approved
            verdict["deducted_amount"] = round(amt - approved, 2)
            verdict["reason"] = (
                "Within meal per-diem." if amt <= remaining_cap
                else f"Exceeds {tier_info['tier']} meal cap of ${cap}/day; excess deducted."
            )
        elif cat == "misc":
            cap = LIMITS["misc_cap_per_day"]
            approved = min(amt, cap)
            verdict["status"] = "ok" if amt <= cap else "over_cap"
            verdict["cap_applied"] = cap
            verdict["approved_amount"] = approved
            verdict["deducted_amount"] = round(amt - approved, 2)
            verdict["reason"] = "Within misc daily cap." if amt <= cap else "Exceeds misc daily cap; excess deducted."
        else:
            # airfare, ground_transport, conference fees, etc. - no hard cap in this mock policy
            verdict["status"] = "ok"
            verdict["approved_amount"] = amt
            verdict["deducted_amount"] = 0.0
            verdict["reason"] = "No cap defined for this category in mock policy; approved as-is pending receipt check."

        total_approved += verdict["approved_amount"]
        total_deducted += verdict["deducted_amount"]
        results.append(verdict)

    return {
        "city_tier": tier_info["tier"],
        "line_results": results,
        "total_claimed": round(total_claimed, 2),
        "total_approved_by_limits": round(total_approved, 2),
        "total_deducted_by_limits": round(total_deducted, 2),
    }


def receipt_completeness_check(expense_lines: list) -> dict:
    """
    Tool 3: Receipt completeness check.
    Flags any line over the receipt threshold that lacks a receipt.
    """
    threshold = LIMITS["receipt_required_above"]
    missing = []
    for line in expense_lines:
        if float(line["amount"]) > threshold and not line.get("has_receipt", False):
            missing.append({
                "category": line["category"],
                "date": line.get("date"),
                "vendor": line.get("vendor"),
                "amount": line["amount"],
            })
    return {
        "receipt_threshold": threshold,
        "missing_receipts": missing,
        "all_required_receipts_present": len(missing) == 0,
    }


def duplicate_detector(employee_name: str, expense_lines: list) -> dict:
    """
    Tool 4: Duplicate detector.
    Compares each line against a mock log of already-processed claims for the
    same employee, matching on (vendor, date, amount).
    """
    suspected_duplicates = []
    for line in expense_lines:
        for past_claim in PROCESSED_LOG:
            if past_claim["employee_name"].lower() != employee_name.lower():
                continue
            for past_line in past_claim["expense_lines"]:
                if (
                    past_line["vendor"].lower() == line.get("vendor", "").lower()
                    and past_line["date"] == line.get("date")
                    and abs(float(past_line["amount"]) - float(line["amount"])) < 0.01
                ):
                    suspected_duplicates.append({
                        "current_line": line,
                        "matched_prior_claim_id": past_claim["claim_id"],
                        "matched_prior_processed_date": past_claim["processed_date"],
                    })
    return {
        "suspected_duplicates": suspected_duplicates,
        "duplicate_count": len(suspected_duplicates),
    }


def output_validator(decision_json: dict) -> dict:
    """
    Tool 5 (optional/fallback): Output validator.
    Sanity-checks the LLM's final structured decision before it's returned -
    e.g. approved_amount should not exceed claimed total, decision must be
    one of the allowed enum values, confidence must be in [0,1].
    """
    errors = []
    allowed_decisions = {"Approve", "Partially Approve", "Reject", "Manual Review"}
    if decision_json.get("decision") not in allowed_decisions:
        errors.append(f"Invalid decision value: {decision_json.get('decision')}")

    conf = decision_json.get("confidence")
    if not isinstance(conf, (int, float)) or not (0 <= conf <= 1):
        errors.append(f"Confidence out of range or missing: {conf}")

    approved = decision_json.get("approved_amount", 0)
    claimed = decision_json.get("total_claimed_amount", 0)
    if isinstance(approved, (int, float)) and isinstance(claimed, (int, float)):
        if approved > claimed + 0.01:
            errors.append("approved_amount exceeds total_claimed_amount")

    return {"valid": len(errors) == 0, "errors": errors}


# Registry used by the agent to map tool name -> callable + JSON schema for OpenAI function calling
TOOL_SCHEMAS = [
    {
    "type": "function",
    "function": {
        "name": "policy_lookup",
        "description": (
            "Look up travel policy sections by keyword. "
            "Pass ALL topics relevant to this claim as a single "
            "comma-separated string - include every expense category "
            "present (e.g. 'meals, lodging, alcohol, airfare, ground transport') "
            "plus cross-cutting concerns like 'receipts, approval thresholds, "
            "manual review, duplicate'. Call this exactly once per claim."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "string",
                    "description": (
                        "Comma-separated keywords to look up. "
                        "Example: 'meals, alcohol, receipts, approval thresholds, manual review'"
                    )
                }
            },
            "required": ["topics"],
        },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "limit_and_perdiem_check",
            "description": "Check each expense line against city-tier lodging/meal/misc caps and ineligible categories. Returns per-line approved/deducted amounts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination_city": {"type": "string"},
                    "expense_lines": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["destination_city", "expense_lines"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receipt_completeness_check",
            "description": "Check whether all expense lines above the receipt threshold have an attached receipt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expense_lines": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["expense_lines"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "duplicate_detector",
            "description": "Check whether any expense line matches a previously processed claim for the same employee (same vendor, date, amount).",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_name": {"type": "string"},
                    "expense_lines": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["employee_name", "expense_lines"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "policy_lookup": policy_lookup,
    "limit_and_perdiem_check": limit_and_perdiem_check,
    "receipt_completeness_check": receipt_completeness_check,
    "duplicate_detector": duplicate_detector,
}
