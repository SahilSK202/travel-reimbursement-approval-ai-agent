# Sahil Corp - Travel & Expense Reimbursement Policy (Mock)

_Version 3.2 - Effective FY2026. For demo/assignment purposes only._

## 1. Eligible Expense Categories
- **Airfare** - Economy class only for domestic; Premium Economy allowed for international flights over 6 hours with manager pre-approval.
- **Lodging** - Reasonable hotel costs, capped per night by city tier (see `limits.json`).
- **Meals** - Per-diem based, capped per day by city tier. No alcohol reimbursement.
- **Ground Transport** - Taxi, rideshare, rental car, train. Mileage reimbursed at $0.67/mile for personal vehicle use.
- **Conference/Registration Fees** - Fully reimbursable with proof of registration.
- **Miscellaneous** - Tips (max $10/day), wifi, parking. Capped at $25/day combined.

## 2. Receipt Requirements
- Receipts are **mandatory** for any single expense line over $25.
- Expenses under $25 may use per-diem or be self-certified, but still require a category and date.
- Missing receipts for required line items must be routed to **Manual Review**, not auto-rejected, unless the claim is clearly fraudulent or duplicated.

## 3. Approval Thresholds
- Claims totaling **$0–$500**: Auto-approve if fully compliant with policy and receipts present.
- Claims totaling **$500.01–$2,000**: Requires policy compliance check; auto-approve only if no exceptions found, otherwise Manual Review.
- Claims **above $2,000**: Always routed to Manual Review regardless of compliance, due to mandatory finance sign-off.

## 4. Common Reasons for Partial Approval or Rejection
- Expense category not eligible (e.g., alcohol, personal entertainment).
- Amount exceeds per-night or per-day limit for the claimant's city tier - excess is deducted, remainder approved.
- Expense date falls outside the approved trip date range.
- Duplicate submission of the same receipt/expense (same vendor, date, and amount as a previously processed claim).
- Missing required receipt for an expense over $25 - routed to Manual Review for documentation follow-up.

## 5. Manual Review Triggers
A claim (or individual line item) must be routed to Manual Review when:
- Total claim exceeds $2,000.
- A required receipt is missing for a line item over $25.
- Conflicting or ambiguous information (e.g., trip dates don't match expense dates, category unclear).
- Suspected duplicate that cannot be confirmed with high confidence.
- Any policy exception is requested (e.g., premium economy without documented pre-approval).

## 6. Per-Diem and Limits
See `limits.json` for the authoritative table of per-night lodging caps and per-day meal caps by city tier, plus the approval matrix.
