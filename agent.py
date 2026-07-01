"""
agent.py
Core agentic loop using the OpenAI API's native tool/function calling.

Flow:
1. System prompt establishes role, the four allowed decisions, and the
   structured output schema.
2. The LLM is given the claim and the tool schemas. It decides which tools
   to call, in what order, possibly calling several before responding.
3. Each tool call + result is appended to the conversation AND to a
   separate `audit_trail` list (for UI display / explainability).
4. Once the LLM stops requesting tools, we make exactly one more call with
   `response_format={"type": "json_object"}` enforced, guaranteeing the
   final answer is valid JSON we can parse directly with `json.loads` -
   no manual text/markdown-fence parsing needed.
5. Hard guardrail rules run AFTER the LLM's output: regardless of what the
   LLM proposed, certain conditions (total > $2000, missing required
   receipt, suspected duplicate, low confidence) force Manual Review. This
   keeps reliability/manual-review handling deterministic rather than
   fully dependent on prompting.
6. output_validator runs as a final structural sanity check.
"""
import json
import os
from openai import OpenAI

from tools import (
    TOOL_SCHEMAS,
    TOOL_FUNCTIONS,
    output_validator,
)

MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Fields that exist only for our own testing/demo purposes and must never be
# sent to the LLM (they would leak the expected answer).
EVAL_ONLY_FIELDS = ["_expected_decision_for_eval", "_note"]


def strip_eval_fields(claim: dict) -> dict:
    """Return a copy of the claim with any eval-only/demo-only fields removed."""
    return {k: v for k, v in claim.items() if k not in EVAL_ONLY_FIELDS}

SYSTEM_PROMPT = """You are a Travel Reimbursement Approval Agent for Sahil Corp.

You will be given a single employee travel reimbursement claim as JSON. Your job is to:
1. Use the available tools to ground your decision in actual policy and rule context.
   You MUST call policy_lookup exactly once, passing ALL expense categories
   present in the claim plus 'receipts', 'approval thresholds', and 'manual review'
   as topics - so all relevant policy sections are retrieved in a single call.
   You MUST call limit_and_perdiem_check, receipt_completeness_check, and duplicate_detector
   for every claim before deciding, even if you're fairly confident, because amounts and
   receipt status must be verified programmatically rather than estimated.
2. Combine the tool results to reach one of exactly four decisions:
   - "Approve": fully compliant, no deductions, no missing info.
   - "Partially Approve": some lines reduced/rejected (e.g. over cap, ineligible category)
     but the claim overall is legitimate and the remainder should be paid.
   - "Reject": the claim is not reimbursable at all (e.g. entirely ineligible expenses,
     clear policy violation with no valid remainder).
   - "Manual Review": information is missing, ambiguous, conflicting, a required receipt is
     absent, a duplicate is suspected, or the total exceeds the policy's manual-review threshold.
     Prefer Manual Review over guessing whenever you are not confident.
3. After tool calls are complete, respond ONLY with a single JSON object (no prose, no markdown
   fences) matching exactly this schema:
{
  "claim_id": string,
  "decision": "Approve" | "Partially Approve" | "Reject" | "Manual Review",
  "total_claimed_amount": number,
  "approved_amount": number,
  "deducted_or_rejected_amount": number,
  "missing_documents": [string],
  "policy_references": [string],
  "reason_codes": [string],
  "confidence": number (0.0 to 1.0),
  "explanation": string (2-4 sentences, plain language, for the employee/approver)
}

Reason code vocabulary (use what applies): MISSING_RECEIPT, OVER_LODGING_CAP, OVER_MEAL_CAP,
OVER_MISC_CAP, INELIGIBLE_CATEGORY, DUPLICATE_SUSPECTED, OVER_MANUAL_REVIEW_THRESHOLD,
DATE_OUT_OF_RANGE, POLICY_EXCEPTION_REQUESTED, FULLY_COMPLIANT.

Be conservative: if tool results conflict or leave ambiguity, choose Manual Review and explain why.
"""


def run_agent(claim: dict, verbose_tool_results=True) -> dict:
    """
    Runs the full agentic loop for a single claim.
    Returns a dict with: final_decision (parsed JSON), audit_trail (list of
    tool calls), raw_messages (full conversation, for debugging).
    """
    client = OpenAI(
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )

    claim = strip_eval_fields(claim)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Evaluate this claim:\n{json.dumps(claim, indent=2)}"},
    ]

    audit_trail = []
    max_iterations = 8
    parsed = None

    for i in range(max_iterations):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        print("message:::",msg)

        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}

                fn = TOOL_FUNCTIONS.get(fn_name)
                if fn is None:
                    result = {"error": f"Unknown tool {fn_name}"}
                else:
                    try:
                        result = fn(**fn_args)
                    except Exception as e:
                        result = {"error": str(e)}

                audit_trail.append({
                    "step": len(audit_trail) + 1,
                    "tool_called": fn_name,
                    "arguments": fn_args,
                    "result": result if verbose_tool_results else "omitted",
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })
            continue

        # No more tool calls requested -> ask once more with JSON mode enforced
        # so we always get back valid, parseable JSON (no manual text-parsing needed).
        messages.append({
            "role": "user",
            "content": "Respond now with ONLY the final JSON object described in your instructions."
        })
        final_response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            response_format={"type": "json_object"},
        )
        try:
            parsed = json.loads(final_response.choices[0].message.content)
        except (json.JSONDecodeError, TypeError):
            parsed = {
                "claim_id": claim.get("claim_id", "UNKNOWN"),
                "decision": "Manual Review",
                "total_claimed_amount": 0,
                "approved_amount": 0,
                "deducted_or_rejected_amount": 0,
                "missing_documents": [],
                "policy_references": [],
                "reason_codes": ["AGENT_OUTPUT_PARSE_FAILURE"],
                "confidence": 0.0,
                "explanation": "Agent failed to produce valid structured output; routed to Manual Review.",
            }
        break

    parsed = _apply_guardrails(parsed, claim, audit_trail)
    validation = output_validator(parsed)
    audit_trail.append({
        "step": len(audit_trail) + 1,
        "tool_called": "output_validator",
        "arguments": {"decision_json": "see final output"},
        "result": validation,
    })
    if not validation["valid"]:
        parsed["decision"] = "Manual Review"
        parsed.setdefault("reason_codes", []).append("OUTPUT_VALIDATION_FAILED")
        parsed["explanation"] = (parsed.get("explanation", "") +
                                  f" [Routed to Manual Review: output validation failed - {validation['errors']}]")

    return {
        "final_decision": parsed,
        "audit_trail": audit_trail,
        "raw_messages": messages,
    }


def _apply_guardrails(parsed: dict, claim: dict, audit_trail: list) -> dict:
    reason_codes = set(parsed.get("reason_codes", []) or [])
    force_manual = False

    total_claimed = parsed.get("total_claimed_amount", 0) or 0
    if isinstance(total_claimed, (int, float)) and total_claimed > 2000:
        force_manual = True
        reason_codes.add("OVER_MANUAL_REVIEW_THRESHOLD")

    if parsed.get("missing_documents"):
        force_manual = True
        reason_codes.add("MISSING_RECEIPT")

    for entry in audit_trail:
        if entry["tool_called"] == "duplicate_detector":
            result = entry.get("result", {})
            if isinstance(result, dict) and result.get("duplicate_count", 0) > 0:
                force_manual = True
                reason_codes.add("DUPLICATE_SUSPECTED")

    confidence = parsed.get("confidence", 1.0)
    if isinstance(confidence, (int, float)) and confidence < 0.6:
        force_manual = True

    if force_manual and parsed.get("decision") != "Manual Review":
        parsed["_original_llm_decision"] = parsed.get("decision")
        parsed["decision"] = "Manual Review"
        parsed["explanation"] = parsed.get("explanation", "") + " [Auto-routed to Manual Review by guardrail rules.]"

    parsed["reason_codes"] = sorted(reason_codes)
    return parsed