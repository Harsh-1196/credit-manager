# Metrics & Quality Indicators - SHG Credit Manager

This document tracks system health, operational SLOs, code coverage, and quality benchmarks for the SHG Credit Manager.

---

## 1. System Performance SLOs (from SPEC Section 17)

| Metric | Target | Measurement Method | Status |
|---|---|---|---|
| List Endpoints p95 Latency | < 300 ms | Middleware request timer & APM | Baseline established (< 25ms local) |
| Schedule & Preview Calculation | < 100 ms | Direct mathematical generator | Benchmarked (< 10ms local) |
| Meeting Collections Batch (20 members) | < 1,000 ms | Integration load benchmark | Phase 4 target |
| Disbursal / Journal Posting Latency | < 250 ms | Transaction timer | Phase 3b target |
| Audit Row Hash Verification Speed | > 10,000 rows/sec | Verifier benchmark (`app.audit.verifier`) | Verified (~22,000 rows/sec) |

---

## 2. Test Coverage & Code Quality Benchmarks (Phase 3b)

| Component | Target Coverage | Tooling | Current Status |
|---|---|---|---|
| Backend Test Suite | 100% Phase 0, 1, 2, 3a & 3b flows | pytest (136 tests) | **136/136 passing** |
| Backend Linting & Formatting | 0 errors | Ruff | **0 errors, clean** |
| Backend Type Checking | Strict, 0 errors | Mypy strict (84 source files) | **0 errors, clean** |
| Frontend Test Suite | Core money, auth, passbook, savings, loans, critical flow | Vitest + RTL (35 tests) | **35/35 passing** |
| Frontend Type Checking | Strict, 0 errors | TypeScript (`tsc --noEmit`) | **0 errors, clean** |
| Frontend Production Build | Zero bundle errors | Vite 5.x build (`tsc && vite build`) | **Built successfully (dist/)** |
| Contrast Accessibility | 100% WCAG AA | WCAG 2.2 Relative Luminance Audit | Verified in `docs/decisions.md` |

---

## 3. Detailed Test Inventory

### 3.1 Backend (136 tests)
- **Loan Disbursal, Repayment & Concurrency (`test_loan_allocation.py`, `test_loan_lifecycle_money.py`, `test_loan_daily_accrual.py`, `test_loan_concurrency.py` - 15 tests)**:
  - Repayment allocation waterfall (Penalty $\rightarrow$ Interest $\rightarrow$ Principal $\rightarrow$ oldest installment first).
  - Partial payments leave status `PARTIAL`.
  - Overpayment prepayment reducing tenure (`REDUCE_TENURE`) by default.
  - Disbursal fails if cash account 1000 is insufficient.
  - Multi-line double-entry posting on disbursal and repayments (`sum(debit) == sum(credit)`).
  - Admin write-off lifecycle with bad debt entry (Debit 5010, Credit 1100).
  - Daily accrual job is strictly idempotent when run twice on same date.
  - Automatic overdue marking, penalty accrual, curing, and loan closing.
  - Portfolio quality queries: PAR 30/60/90, total active principal, total arrears.
  - Concurrency stress tests: 2 simultaneous repayments and 20 parallel asynchronous repayments on a single loan without deadlock or ledger imbalance.
- **Loan Domain & Schedule (`test_loan_schedule.py` - 7 tests)**:
  - Reducing Balance Known-Answer (SPEC 6.3): Principal 50,000, 12% p.a., 12 months $\rightarrow$ EMI 4,442.44; month 12 absorbs 1-paisa residue; principal parts sum to exactly 50,000.00; final balance 0.00.
  - Flat Rate Known-Answer (SPEC 6.3): Principal 10,000, 12% p.a., 10 months $\rightarrow$ total interest 1,000.00; monthly installment 1,100.00.
  - Zero interest rate loan (0% rate divides principal evenly with 0 interest).
  - Single-month tenure edge case.
  - Odd tenure amortization and fractional residue absorption (e.g. 7 months).
  - Large principal loan (e.g. 5,00,000 over 36 months).
  - **Hypothesis property tests** over 50 randomized iterations of principals (100 to 1,000,000), tenures (1 to 60), and rates (0% to 36%): `sum(principal_due) == principal` strictly holds, `total_due == principal_due + interest_due` for each row, and final balance is strictly 0.00.
- **Loan Lifecycle, State Machine & Maker-Checker (`test_loan_lifecycle.py` - 76 tests)**:
  - **Exhaustive State Machine Matrix (70 tests)**: Testing all 81 pairs of `(from_status, to_status)`; all 70 invalid state transitions strictly raise `LOAN_INVALID_TRANSITION`.
  - **Maker-Checker Enforcement**: Creator (`applied_by`) attempting approval raises `MAKER_CHECKER_VIOLATION`; applicant member (`member.user_id`) attempting approval raises `MAKER_CHECKER_VIOLATION`; another leader or ADMIN succeeds.
  - **Rejection Reason**: Rejecting without a non-empty reason raises `REASON_REQUIRED`.
  - **Optimistic Locking**: Approval with stale `expected_version` raises `OPTIMISTIC_LOCK_CONFLICT` (HTTP 409).
  - **Eligibility Blocker Engine**: Inactive / exited member raises blocker; savings multiple exceeding 4x cap blocks submission with `LOAN_INELIGIBLE`.
  - **Full HTTP API Lifecycle**: `/loans/preview-schedule` $\rightarrow$ `POST /loans` (draft) $\rightarrow$ `POST /loans/{id}/submit` $\rightarrow$ `GET /loans/{id}` (maker-checker flag) $\rightarrow$ `POST /loans/{id}/approve` $\rightarrow$ `GET /loans/{id}/history` (audit trail).
- **Ledger & Double-Entry (`test_ledger.py`, `test_ledger_properties.py` - 8 tests)**:
  - Balanced journal entry posting (`sum(debit) == sum(credit)`).
  - Unbalanced journal entry rejection (`LEDGER_UNBALANCED_ENTRY`).
  - Debit XOR credit line side constraint (`LEDGER_INVALID_LINE_SIDE`).
  - Mirror reversal entry creation with `reverses_entry_id` link.
  - Double reversal rejection (`ENTRY_ALREADY_REVERSED`) and prohibition against reversing a reversal.
  - Ledger database & ORM level immutability (prohibition of UPDATE and DELETE).
  - Hypothesis property tests for ledger zero-sum trial balance.
- **Savings & Passbook (`test_savings.py` - 5 tests)**:
  - Dues generation per active member per period without duplication.
  - Late fine calculation with 5 grace days and monthly dues cap.
  - Savings collection posting balanced journal entries and updating dues to PAID.
  - Savings withdrawal enforcing sufficient savings balance.
  - Idempotency replay returns identical cached response without double-posting; conflicting request payload returns 409 Conflict.
- **Auth & Access Control (`test_auth.py`, `test_authorization.py` - 15 tests)**:
  - Login lockout after 5 failures, refresh token rotation, token reuse family revocation, logout revocation.
  - Parametrized role matrix for users, groups, settings, member enrollment.
  - Cross-group access returning 404 (not 403).
  - PII masking of phone and address for AUDITOR and non-self MEMBER.
- **Audit & Platform (`test_audit.py`, `test_health.py` - 10 tests)**:
  - Tamper-evident hash-chain audit logging and `verify_audit_chain` detection.
  - Health, ready, request ID propagation, uniform error responses.

### 3.2 Frontend (35 tests)
- `LoanDetailPage.test.tsx` (4 tests):
  - Renders Screen 8 3-column layout: timeline (left), schedule table (center), summary balances (right).
  - Displays `"Overdue N days"` explicit text cue for past-due installments (not color alone).
  - Disburse dialog restates member, net amount, group cash balance, and shows the balanced double-entry journal lines to be posted.
  - Repayment dialog shows live debounced repayment allocation preview (penalty, interest, principal, prepayment).
- `ApproveAndDisburseFlow.test.tsx` (1 test):
  - Critical end-to-end integration flow: Maker-checker review in approvals queue $\rightarrow$ checker approves $\rightarrow$ navigation to loan detail $\rightarrow$ reviews journal preview $\rightarrow$ disburses loan $\rightarrow$ schedule activated.
- `ApprovalsQueue.test.tsx` (4 tests):
  - Renders pending applications queue (`status === "SUBMITTED"`).
  - Enforces maker-checker rule: Creator has disabled Approve button with explicit explanation note (`[MAKER-CHECKER RESTRICTION]`).
  - Allows approving permitted loan and submits with expected version.
  - Reject button requires non-empty explanation reason before submitting.
- `LoanSchedulePreview.test.tsx` (3 tests):
  - Renders application form inputs.
  - Displays eligibility checks with explicit text cues (`[PASS]`, `[FAIL]`, `[WARN]`, `[INFO]`), not color alone.
  - Renders schedule preview table with right-aligned tabular numerals (`MoneyText`) and totals summary row.
- `MoneyText.test.tsx` (11 tests): Indian grouping (`en-IN`), 2 decimal places, tabular numerals, negative sign formatting.
- `SidebarRoleScoping.test.tsx` (4 tests): Scoped navigation for ADMIN, GROUP_LEADER, AUDITOR, and MEMBER roles.
- `LoginPage.test.tsx` (3 tests): Editorial design layout, validation errors, and submission.
- `RecordSavingsModal.test.tsx` (2 tests): Validation and 2-step confirmation with client-side idempotency key.
- `MemberPassbookTab.test.tsx` (3 tests): Ruled-ledger style, separated debit and credit columns, ADMIN reversal flow.
