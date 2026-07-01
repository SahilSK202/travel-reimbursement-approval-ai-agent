# Travel Reimbursement Approval Agent

A working prototype of a GenAI/Agentic travel reimbursement approval system.
The OpenAI model decides which tools to call (policy lookup, per-diem/limit
checker, receipt completeness check, duplicate detector), combines the
results, and returns a structured decision. A deterministic guardrail layer
runs after the LLM to force Manual Review on high-risk conditions, and an
output validator catches malformed results. A Streamlit UI shows the
decision, an editable claim input, and a full audit trail of every tool call.

See [Demo Evidence](DEMO_EVIDENCE.md) for annotated screenshots of all decision types and UI features.
![Approve Decision](screenshots/03_approve_decision.png)
## 1. Setup

```bash
cd travel_reimbursement_agent
python -m venv venv && source venv/bin/activate    # optional but recommended
pip install -r requirements.txt
cp .env.example .env                                 # then edit .env and add your real key
```

Required environment variable:
- `GROQ_API_KEY` - free API key from [console.groq.com](https://console.groq.com/keys) (no billing info required for the free tier).
- `GROQ_MODEL` (optional, defaults to `llama-3.3-70b-versatile`) - any Groq-hosted model that supports tool calling.

The agent uses the standard `openai` Python SDK pointed at Groq's OpenAI-compatible endpoint
(`https://api.groq.com/openai/v1`), so no extra SDK is required and the tool-calling code is
identical to what you'd write against the real OpenAI API.

## 2. Running the demo

**Streamlit UI (primary demo):**
```bash
streamlit run app.py
```
Opens at `http://localhost:8501`. Pick a sample claim from the sidebar (or paste custom claim
JSON), click **Run Evaluation**, and the decision card, metrics, reason codes, and audit trail
render in the main panel. Running multiple claims in one session builds a small "insights" table
and bar chart at the bottom of the page.

**Headless evaluation script:**
```bash
python eval.py
```
Runs all 5 sample claims through the agent, prints PASS/FAIL against the expected decision for
each, and writes full results (decisions + audit trails) to `sample_outputs/eval_results.json`.

**CLI for a single claim** (optional, useful for debugging):
```python
python -c "
import json
from agent import run_agent
claim = json.load(open('data/sample_claims.json'))[0]
print(json.dumps(run_agent(claim)['final_decision'], indent=2))
"
```

## 3. Project structure

```
travel_reimbursement_agent/
├── app.py                  # Streamlit UI
├── agent.py                # Agent loop: OpenAI tool calling + guardrails + validation
├── tools.py                # Tool functions: policy_lookup, limit_and_perdiem_check,
│                           # receipt_completeness_check, duplicate_detector, output_validator
├── eval.py                 # Headless batch evaluation script
├── data/
│   ├── travel_policy.md    # Mock policy document (context grounding source)
│   ├── limits.json         # Per-diem caps, approval matrix, ineligible categories
│   ├── sample_claims.json  # 5 sample claims (approve/partial/reject/manual review/duplicate)
│   └── processed_claims_log.json  # Mock "already processed" claims for duplicate detection
├── outputs/                # eval.py writes results here
├── sample_outputs/         # Pre-generated JSON outputs for 4 claim scenarios including full audit trails
├── requirements.txt        # Python dependencies - install with: pip install -r requirements.txt
├── .env.example            # Template for required environment variables - copy to .env and add your GROQ_API_KEY
├── screenshots/            # Screenshots of the live Streamlit app covering all decision types and UI features
├── DEMO_EVIDENCE.md        # Annotated walkthrough of each screenshot explaining the feature it demonstrates
└── ASSUMPTIONS.md          # List of assumptions made, simplifications applied, known gaps, and suggested next improvements
```

## 4. Design choices and trade-offs

- **Plain OpenAI tool-calling instead of a framework (LangChain/CrewAI):** keeps the agent loop
  transparent and easy to explain/debug. The loop is ~40 lines in
  `agent.py`: ask model → if it requests tools, run them and feed results back → repeat until it
  returns final JSON. This trades some "out of the box" features (e.g. built-in tracing) for
  clarity and fewer moving parts to break in a timeboxed build.
- **Policy lookup via keyword search over Markdown, not a vector DB:** the policy document is
  small and fixed for this assignment, so a lightweight keyword search is sufficient and avoids
  adding an embeddings/vector-store dependency. In a production system with larger or frequently
  changing policy docs, this would become a proper RAG retrieval step.
- **Deterministic guardrails layered after the LLM:** the LLM proposes a decision, but hard rules
  (total > $2,000, any missing required receipt, any suspected duplicate, confidence < 0.6) force
  Manual Review regardless of what the model said. This was a deliberate choice to satisfy the
  "reliability" evaluation criterion - manual review handling shouldn't depend entirely on the
  LLM remembering to apply every rule correctly every time.
- **`output_validator` as a final tool, not just an LLM self-check:** decision enum, confidence
  range, and approved-amount-vs-claimed-total are checked in code after generation. Any failure
  forces Manual Review rather than letting a malformed structured output reach the user.
- **Streamlit over a custom frontend:** fastest path to a usable, inspectable UI (decision cards,
  metrics, expandable audit trail, session history table/chart) without spending build time on
  frontend plumbing.

## 5. Assumptions and limitations

- All policy, limit, and claim data is mocked for this assignment; no real employee or company
  data is used.
- The duplicate detector only compares against a small static `processed_claims_log.json`, not a
  real claims database, and matches on exact (vendor, date, amount) - it would miss near-duplicates
  with slightly different amounts or vendor name formatting.
- Trip-date-vs-expense-date validation (flagging expenses outside the trip window) is described in
  the policy and reason-code vocabulary but not implemented as a dedicated tool; the LLM can
  flag this via `policy_lookup` + reasoning, but it isn't independently verified in code the way
  limits/receipts/duplicates are. This would be a natural next tool to add.
- Currency is assumed to be a single currency (USD) throughout; no FX conversion.
- **Groq (free tier) instead of paid OpenAI:** the agent uses the `openai` SDK pointed at Groq's
  OpenAI-compatible endpoint, running `llama-3.3-70b-versatile` by default, which supports native
  tool calling. This required zero changes to the tool-calling loop itself - only the client's
  `base_url`/`api_key` and the model name changed - which is itself a useful demonstration that
  the agent logic is provider-agnostic. Swapping back to real OpenAI, or to Anthropic, would be a
  similarly small change.
- The Streamlit app keeps session history in memory only (no persistent database); restarting the
  app clears history.


## 6. Optional enhancements implemented

- ✅ **Simple UI:** Streamlit app with decision dashboard, metrics, and session-level insights
  (table + bar chart of decisions across runs).
- ✅ **Audit trail:** every tool call (name, arguments, result) is captured in `audit_trail` and
  rendered as expandable steps in the UI, plus included in `eval_results.json`.
- ✅ **Evaluation script:** `eval.py` runs all sample claims and checks actual vs. expected decision.
- ✅ **Confidence score + reason codes:** every decision includes a `confidence` float and a
  structured `reason_codes` list from a fixed vocabulary (see `agent.py` system prompt).
- ⏭️ **MCP-based tool integration:** not implemented in this timebox. The four tool functions in
  `tools.py` are already structured as discrete, schema-described capabilities, so converting
  `policy_lookup` (the best candidate, since it's the most likely to be reused by other agents)
  into an MCP server would mainly mean wrapping it with an MCP server SDK and exposing the same
  function signature - a natural next step if more time were available.

For a full list of design trade-offs and known gaps, see [Assumptions & Limitations](ASSUMPTIONS.md).

