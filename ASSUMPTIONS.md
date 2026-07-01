# Assumptions, Simplifications, Known Gaps & Next Steps

## Assumptions

- **Single currency (USD):** All claim amounts are in USD. No FX conversion is applied.
- **Mock data only:** All policy documents, claims, receipts, and employee data are fictional. No real employee or company data is used anywhere.
- **One employee per claim:** Each claim belongs to a single employee; split-expense or group travel claims are out of scope.
- **Static policy:** The travel policy does not change during a session. A document version update would require a server restart.
- **Receipt presence is boolean:** `has_receipt: true/false` is taken at face value. The agent does not verify receipt authenticity or image content.
- **Duplicate detection is exact-match only:** Matches on vendor name, date, and amount within $0.01 tolerance. Assumes vendor names are consistently formatted.
- **City tier lookup is case-insensitive exact name match:** "New York" matches but "NYC" or "New York City" would fall through to Tier 3 (default). A real system would use a geocoding API.
- **Meal cap is per calendar day, not per 24-hour window:** Two meals on the same date share one daily cap regardless of time.

---

## Simplifications

- **Policy lookup is keyword search over Markdown, not vector/RAG retrieval.** Sufficient for a small fixed document; would not scale to a multi-page policy corpus without an embeddings layer.
- **The "processed claims log" (duplicate detector) is a static JSON file**, not a real database query. In production this would be a SQL/NoSQL lookup against a claims management system.
- **No authentication or multi-user isolation.** The Streamlit app has no login; session history is in-memory only and clears on restart.
- ** `llama-3.3-70b-versatile` from `groq` is used as default.** Stronger models would improve edge-case reasoning quality but at higher token cost.
- **Approval matrix is flat.** No distinction between employee seniority levels, department budgets, or manager vs. director approval chains.

---

## Known Gaps

| Gap | Impact | Effort to fix |
|---|---|---|
| Trip-date vs expense-date validation | Expenses outside the trip window are not caught by a dedicated tool - only by LLM reasoning | Low - add a `date_range_validator` tool |
| Near-duplicate detection | Different amount or minor vendor name variation not caught | Medium - fuzzy matching (e.g. Levenshtein distance on vendor names) |
| Receipt image/content verification | `has_receipt: true` is self-reported; no OCR or image check | High - would need a document AI service |
| Multi-currency support | International trips with non-USD receipts not handled | Medium - FX API lookup tool |
| Mileage reimbursement calculator | Policy defines $0.67/mile but no tool calculates mileage claims | Low - add a `mileage_calculator` tool |
| Persistent audit log / history | Session history lost on app restart | Low - SQLite or file-backed store |
| City tier alias resolution | "NYC", "SF", "Chi" won't resolve to Tier 1/2 cities | Low - alias dict or geocoding |

---

## What I Would Improve Next (Priority Order)

1. **Add `date_range_validator` tool** - deterministically flag any expense line whose date falls outside `trip_start_date` to `trip_end_date`. Currently relies on LLM reasoning, which is less reliable than code.

2. **Replace keyword policy lookup with proper RAG** - chunk the policy into sections, embed them with a small embedding model (e.g. `text-embedding-3-small`), store in a local vector store (ChromaDB or FAISS), and retrieve the top-k most relevant chunks per claim. This scales to larger policy documents and handles synonym mismatches.

3. **Add streaming output to the Streamlit UI** - show each tool call result appearing live as the agent runs rather than showing everything at once after a spinner. Makes the agent's reasoning process much more visible and impressive in a demo.

4. **Wire `policy_lookup` as an MCP server** - the function already has a clean schema. Converting it to an MCP server (`@mcp.tool`) would let any MCP-compatible agent or IDE (e.g. Cursor, Claude Desktop) call it directly, enabling reuse across multiple agent workflows without code duplication.

5. **Add per-employee approval matrix** - route claims above certain thresholds to different approvers (line manager → finance → CFO) based on employee level, department, or trip purpose, rather than a single flat $2,000 threshold.

6. **Add evaluation scoring beyond pass/fail** - currently `eval.py` checks if the decision matches the expected value. Adding a rubric (e.g. approved amount within ±5%, reason codes match expected set) would give a richer picture of model quality across model swaps.
