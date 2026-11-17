# Architectural Decision Records (ADR) - SHG Credit Manager

This document records the foundational architectural decisions, financial domain trade-offs, and implementation assumptions adopted across the design and engineering of the **SHG Credit Manager**.

---

## 1. System-Wide & Core Banking Invariants

### 1.1 Strict Float Elimination & Money Representation
- **Question**: How should currency values be represented across database storage, backend calculation, and frontend presentation?
- **Decision**: Store as PostgreSQL `NUMERIC(14,2)`, manipulate exclusively as Python `Decimal` quantized with `ROUND_HALF_UP`, exchange over JSON as exact decimal strings (e.g., `"18450.00"`), and calculate client-side totals exclusively via `decimal.js`.
- **Reasoning**:
  1. IEEE 754 binary floating-point numbers (`float`, `double`, JavaScript `Number`) cannot represent fractional base-10 values (like ₹0.10 or ₹0.01) precisely, introducing cumulative penny/paisa drift.
  2. Financial core banking systems require exact reconciliations to the paisa. Using strings across JSON and `Decimal` across domains guarantees zero float leakage.

### 1.2 Append-Only Ledger & Reversals Only
- **Question**: Should ledger journal entries or lines ever be modified (`UPDATE`) or removed (`DELETE`) when an error occurs?
- **Decision**: Strictly append-only. No `UPDATE` or `DELETE` grants on `journal_entries` and `journal_lines`. Corrections require a mirror reversal voucher referencing the original entry ID (`reverses_entry_id`). An entry may only be reversed once.
- **Reasoning**:
  1. SPEC Section 4.5 and standard banking accounting standards require an unbroken historical audit trail.
  2. If an entry is reversed, the mirror entry swaps debits and credits, preserving the historical trail and providing full transparency for group members and auditors.

### 1.3 Scoped HTTP 404 Instead of 403 for Tenant Isolation
- **Question**: When a user queries a group, member, loan, or meeting outside their assigned scope, should the API return HTTP 403 Forbidden or HTTP 404 Not Found?
- **Decision**: Return **HTTP 404 Not Found**.
- **Reasoning**:
  1. Information disclosure prevention: Returning HTTP 403 acknowledges that the resource ID exists in the database, allowing malicious actors to enumerate group IDs, member UUIDs, or loan numbers.
  2. Returning HTTP 404 makes unauthorized cross-tenant resources indistinguishable from non-existent resources.

### 1.4 Cryptographic SHA-256 Audit Chaining with Canonical JSON
- **Question**: How to guarantee tamper-evidence for system audit logs across diverse database engines without vendor-specific blockchain features?
- **Decision**: Every audit row computes `row_hash = SHA256(prev_hash || canonical_json(entry))` where timestamps are UTC-normalized (`YYYY-MM-DDTHH:MM:SS.ffffffZ`) and JSON keys are lexicographically sorted.
- **Reasoning**:
  1. Database administrators or attackers with direct SQL access cannot tamper with historical records without breaking the cryptographic hash chain.
  2. Field supervisors and independent auditors can verify the entire audit log in seconds using `python -m app.audit.verifier`.

---

## 2. Credit Amortization & Repayment Decisions

### 2.1 Final Month Rounding Residue Absorption
- **Question**: How should amortization rounding residues (1–2 paise) be handled on monthly installments?
- **Decision**: The final installment $n$ absorbs all cumulative rounding residue:
  $$\text{principal}_n = \text{principal} - \sum_{i=1}^{n-1} \text{principal}_i$$
  $$\text{interest}_n = \text{total\_interest} - \sum_{i=1}^{n-1} \text{interest}_i \quad (\text{flat}) \quad \text{or} \quad \text{round}(\text{outstanding}_{n-1} \times r, 2) \quad (\text{reducing})$$
  $$\text{total\_due}_n = \text{principal}_n + \text{interest}_n$$
- **Reasoning**:
  1. Assures $\sum \text{principal\_due} = \text{principal}$ strictly, with final loan balance reaching exactly ₹0.00.
  2. Matches SPEC Section 6.3 known-answer benchmarks (e.g. Reducing P=50,000, 12%, 12m $\rightarrow$ month 12 absorbs 1 paisa to yield exactly ₹4,442.43).

### 2.2 Prepayment Curtailment Default: Reduce Tenure
- **Question**: When a member overpays beyond the current installment due, should the prepayment reduce loan tenure or future installment amounts?
- **Decision**: **Reduce tenure** by default (`REDUCE_TENURE`).
- **Reasoning**:
  1. Standard micro-lending practice (SPEC Section 6.4 & 19.1).
  2. Shortens loan duration and saves maximum interest for rural women borrowers.
  3. Keeps group collection sheets predictable since monthly EMI amounts remain constant.

### 2.3 Repayment Allocation Waterfall
- **Question**: When a repayment is received, what is the exact order of debt allocation?
- **Decision**: Strict waterfall on the oldest active/overdue installment:
  1. **Late Fines & Penalties Due** (Account 4010)
  2. **Interest Due** (Account 4000)
  3. **Principal Due** (Account 1100)
- **Reasoning**:
  1. Conforms to Indian micro-credit regulatory guidelines ensuring penalties and interest are satisfied before reducing loan principal balance.
  2. Handled atomically in a single multi-line double-entry journal entry.

### 2.4 Maker-Checker Segregation of Duties
- **Question**: Can an SHG leader approve their own loan application?
- **Decision**: **Strictly prohibited**. The creator (`applied_by`) or applicant (`member.user_id`) cannot approve their own loan.
- **Reasoning**:
  1. Prevents self-dealing, fraud, and internal collusion.
  2. Backend state machine and endpoints raise `MAKER_CHECKER_VIOLATION` (HTTP 400/403). The frontend explicitly computes `can_approve` and shows a guidance note indicating another leader or admin must approve.

### 2.5 Optimistic Concurrency Control for Loan State
- **Question**: How to prevent race conditions when two leaders review and approve/reject a loan simultaneously?
- **Decision**: Each loan record maintains an integer `version` field. State transitions require `expected_version` and increment `version += 1`.
- **Reasoning**:
  1. Stale client updates raise `OPTIMISTIC_LOCK_CONFLICT` (HTTP 409) without corrupting data or double-disbursing funds.

---

## 3. Operations, Meetings & Distributed Systems Decisions

### 3.1 All-or-Nothing Meeting Batch Collections Atomicity
- **Question**: If one member's record in a 20-member meeting collection has an error, should the remaining 19 be saved?
- **Decision**: **Strict all-or-nothing rollback**.
- **Reasoning**:
  1. Physical cash parity: In rural assembly meetings, cash is collected and counted into the physical cash box as a single batch. Partial recording creates a mismatch between digital records and physical cash in the box.
  2. Replays using the same idempotency key are safe and clean once the input error is corrected.

### 3.2 Granular Double-Entry Posting (One Balanced Entry Per Member)
- **Question**: Should a 20-member meeting collection generate one massive 80-line journal entry or individual member entries?
- **Decision**: **One distinct, balanced journal entry per member**.
- **Reasoning**:
  1. Member savings passbooks directly query entries for sub-account `2000-{member}` without parsing group splits.
  2. Administrative corrections or reversals can reverse an individual member's collection entry without invalidating the entire group's meeting history.

### 3.3 Transactional Outbox for Asynchronous Read Models
- **Question**: How should dashboard aggregates, PAR 30/60/90 metrics, and overdue figures be updated without slowing down financial transaction commits?
- **Decision**: **Transactional Outbox with ARQ Worker and Redis**.
- **Reasoning**:
  1. Prevents dual-write bugs: Outbox events are committed in the same PostgreSQL transaction as ledger lines.
  2. Decouples heavy calculation from row-level locks on loans and accounts.
  3. Consumers use composite uniqueness `(consumer_name, event_id)` for idempotent deduplication.

### 3.4 Defense-in-Depth Row-Level Security
- **Question**: Is application-level scoping (`WHERE shg_id = :id`) sufficient?
- **Decision**: Add **PostgreSQL Row-Level Security (RLS)** as defense-in-depth.
- **Reasoning**:
  1. Session settings (`SET LOCAL app.permitted_group_ids = '...'`) enforce database-level isolation.
  2. Accidental unfiltered SQL queries or developer bugs cannot leak cross-group data.

---

## 4. AI Assistant & Security Decisions

### 4.1 Strictly Read-Only AI Tools & Zero-Write Invariant
- **Question**: Should the AI assistant be allowed to post journal entries or disburse loans directly?
- **Decision**: **Strictly forbidden**. The LLM never writes to the ledger or database tables.
- **Reasoning**:
  1. Eliminates prompt injection risk from triggering unauthorized money movements or wiping debt.
  2. Tools run with caller identity and validate group scope, returning HTTP 404 on cross-tenant probes.

### 4.2 Human-in-the-Loop for Meeting Notes Extraction
- **Question**: When meeting notes are parsed by AI, should collections be recorded automatically?
- **Decision**: Returns an **in-memory draft only**.
- **Reasoning**:
  1. Ambiguous and unmatched member names are flagged explicitly (`ambiguous_members`, `unmatched_items`) without guessing.
  2. The group leader reviews pre-filled cells on the collection grid and manually confirms the submission.
