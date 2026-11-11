# Architectural Decision Records (ADR) - SHG Credit Manager

## Status
Living document. Recorded decisions and defaults adopted during Phase 0, 1, 2, and 3a.

---

## 1. Open Decisions from SPEC Section 19

### 1.1 Decision 1: Prepayment Behavior Default
- **Question**: When a member overpays beyond the current installment due, should the prepayment reduce the loan tenure or reduce the future installment amounts?
- **Decision**: **Reduce tenure**.
- **Reasoning**:
  1. Spec default: In Section 6.4 and 19.1, reducing tenure is the stated standard practice for SHG and micro-lending programs.
  2. Interest savings: In reducing balance loans, keeping EMI constant and reducing tenure maximizes the interest savings for the rural woman borrower, shortening debt duration.
  3. Accounting simplicity: Monthly collection sheets remain predictable for group leaders since the regular EMI amount remains constant until the loan finishes earlier than expected.
  4. Flexibility: Group settings can override this per group (`group_settings.prepayment_behavior`), but the system default is set to `REDUCE_TENURE`.

### 1.2 Decision 2: Interest Accrual Mechanism
- **Question**: Whether interest is accrued daily or recognized per installment period?
- **Decision**: **Recognized per installment** (accrued at installment due date / schedule period).
- **Reasoning**:
  1. Spec default: Section 19.2 recommends recognition per installment.
  2. SHG meeting cadence: Self-Help Groups operate on discrete meeting cycles (typically monthly or fortnightly). Accounting ledgers and passbooks reflect installment schedule dates rather than daily accrued micro-fractions.
  3. Daily penalties: Late penalties continue to accrue daily after grace periods via the daily job (as specified in Section 6.5), keeping loan arrears accurate while keeping base interest aligned with schedule installments.

### 1.3 Decision 3: PDF Generation Library for Backend
- **Question**: WeasyPrint vs. ReportLab for backend statement, passbook, and collection sheet export?
- **Decision**: **ReportLab**.
- **Reasoning**:
  1. Cross-platform portability: ReportLab has zero external non-Python system dependencies (such as libpango, libcairo, libgdk-pixbuf), running cleanly on lightweight Docker alpine/slim containers, macOS, and Windows.
  2. Performance: ReportLab is significantly faster for structured multi-page tabular ledger and collection sheet generation than browser/layout engine wrappers.
  3. Reliability: Generates precise vector tables, ruled lines, and page numbers needed for the "ruled-ledger" passbook format.

### 1.4 Decision 4: Daily Job Scheduler
- **Question**: APScheduler in-process vs. external CLI command executed by cron/orchestrator?
- **Decision**: **Dual architecture — APScheduler in-process scheduler with standalone CLI command (`python -m app.jobs.daily_accrual`)**.
- **Reasoning**:
  1. Development & Single-container convenience: In local Docker and single-instance deployments, APScheduler starts with the FastAPI lifecycle without requiring external cron daemons.
  2. Production & Multi-worker safety: In distributed environments with multiple web workers (e.g. Uvicorn/Gunicorn workers), running schedulers in every web worker leads to race conditions. A CLI entry point allows standard container orchestrators (Kubernetes CronJob or Linux crontab) to trigger the job independently with distributed locking or idempotency keys.

---

## 2. Phase 3a: Loan Domain & Maker-Checker Decisions

### 2.1 Loan Repayment Schedule & Rounding Residue Absorption
- **Requirement**: Amortization schedules for both Reducing Balance (EMI) and Flat Rate must satisfy `sum(principal_due) == principal` exactly, with zero balance upon completion.
- **Decision**:
  - All internal calculations use `Decimal` quantized with `ROUND_HALF_UP` to 2 decimal places.
  - The final installment $n$ computes:
    $$\text{principal}_n = \text{principal} - \sum_{i=1}^{n-1} \text{principal}_i$$
    $$\text{interest}_n = \text{total\_interest} - \sum_{i=1}^{n-1} \text{interest}_i \quad \text{(flat) or } \text{round}(\text{outstanding} \times r, 2) \quad \text{(reducing)}$$
    $$\text{total\_due}_n = \text{principal}_n + \text{interest}_n$$
  - Absorbs any 1–2 paisa rounding residue so the ledger remains balanced to the paisa.
  - Verified with SPEC 6.3 known-answers:
    - Reducing: P=50,000, 12% p.a., 12 months $\rightarrow$ EMI 4,442.44; month 12 absorbs 1 paisa (4,398.45 principal + 43.98 interest = 4,442.43).
    - Flat: P=10,000, 12% p.a., 10 months $\rightarrow$ total interest 1,000.00; monthly installment 1,100.00 (1,000 principal + 100 interest).
  - Tested across arbitrary principals and tenures via Hypothesis property tests.

### 2.2 Maker-Checker Segregation of Duties
- **Requirement**: The creator (`applied_by`) or applicant (`member.user_id`) cannot approve their own loan.
- **Decision**:
  - Backend enforcement: In `LoanStateMachine.transition` and endpoint handlers, if `actor.id == loan.applied_by` or `loan.member.user_id == actor.id`, the action raises `MAKER_CHECKER_VIOLATION` (HTTP 403/400).
  - Frontend contract: `can_approve: boolean` and `maker_checker_note: string | null` are computed and returned on `GET /loans/{id}` and `GET /loans`. The UI disables the Approve button and displays the note explicitly next to the control, guiding another leader or admin to approve.

### 2.3 Optimistic Concurrency Control
- **Requirement**: Concurrent approval or modification conflicts must be detected and rejected without data corruption.
- **Decision**:
  - The `loans` table maintains an integer `version` column.
  - Every valid state machine transition increments `loan.version += 1`.
  - Approve and reject requests accept an expected `version` argument. If `loan.version != expected_version`, an `OPTIMISTIC_LOCK_CONFLICT` (HTTP 409) is raised with current and expected versions in error details.

### 2.4 Eligibility Engine Severity Model
- **Requirement**: SPEC 6.2 eligibility checks evaluated at application submission.
- **Decision**:
  - Structured result schema: `code`, `name`, `passed`, `severity`, `message`, `actual_value`, `threshold_value`.
  - Severity `BLOCKER`:
    - `MEMBER_ACTIVE`: Member must be in ACTIVE status.
    - `CONCURRENT_LOANS`: Member must not exceed concurrent active loan limits.
    - `SAVINGS_MULTIPLE`: Principal $\le \text{max\_loan\_multiple} \times \text{member savings balance}$.
    - `TENURE_POLICY`: Tenure between `min_tenure_months` and `max_tenure_months`.
    - `OVERDUE_REPAYMENTS`: Member has no overdue installments.
    - If any blocker fails, submission is rejected with `LOAN_INELIGIBLE` (HTTP 400).
  - Severity `WARNING`:
    - `GROUP_LIQUIDITY`: Principal $\le$ available liquid cash (Cash Account 1000 + Bank 1010). If group cash is temporarily lower, it serves as a warning for approvers rather than a hard block, allowing approval before external grant/bank funds arrive.
  - Text cues: In accordance with accessibility rules ("Color is never the only signal for overdue or negative values"), every check displays an explicit text cue (`[PASS]`, `[BLOCKER FAIL]`, `[WARNING]`, `[INFO]`).

---

## 3. Phase 3b: Money Movement, Repayment Allocation & Concurrency Decisions

### 3.1 Repayment Allocation Waterfall
- **Requirement**: SPEC 6.4 repayment allocation hierarchy and multi-installment handling.
- **Decision**:
  - Exact order of waterfall application:
    1. **Penalty Due** (Account 4010 Penalty / Late Fine Income)
    2. **Interest Due** (Account 4000 Loan Interest Income)
    3. **Principal Due** (Account 1100 Loans Receivable)
  - Evaluated on the oldest active/overdue installment first.
  - Partial payments update `principal_paid` / `interest_paid` / `penalty_paid` and leave the installment status as `PARTIAL`.
  - Overpayment exceeding current due principal flows down to the next installment. Any prepayment beyond total scheduled due principal is absorbed as curtailment against future principal installments, shortening tenure by default (`REDUCE_TENURE`).
  - Single atomic journal entry posted for the repayment:
    - Debit Cash Account 1000 (total payment amount)
    - Credit Member Loans Receivable 1100 (principal allocated)
    - Credit Interest Income 4000 (interest allocated)
    - Credit Penalty Income 4010 (penalty allocated)
    - $\text{Debit} = \text{Credit}$ guaranteed to the paisa.

### 3.2 Concurrency Defense & Idempotency
- **Requirement**: Prevent double-posting or race conditions when two repayments or disbursal events hit concurrently.
- **Decision**:
  - `SELECT ... FOR UPDATE` row-level locks acquired inside transaction on both the `Loan` row and group `Account` (Cash 1000) row before balance evaluation.
  - Idempotency key stored atomically with request payload hash. Concurrent identical replays return the cached response; conflicting payloads under the same key return HTTP 409.
  - Verified with 20 parallel asynchronous repayments on a single loan in automated concurrency stress testing without deadlocks or ledger imbalances.

### 3.3 Daily Accrual Job Idempotency
- **Requirement**: Daily penalty calculation runnable safely via CLI or scheduler multiple times without duplicate charges.
- **Decision**:
  - Each `LoanSchedule` row records `last_penalty_accrual_date`.
  - Daily job computes elapsed days between `max(due_date + grace_days, last_accrual_date)` and run date. If already accrued as of target date, elapsed days is 0 and ₹0.00 is added.
  - Closed periods (`PAID`, `CLOSED`, `WRITTEN_OFF`) are completely skipped.
  - State transitions: automatically transitions `ACTIVE -> OVERDUE` after grace days, cures `OVERDUE -> ACTIVE` when overdue amounts are fully cleared, and transitions to `CLOSED` when all principal, interest, and penalties are paid down to 0.

### 3.4 Write-Off Accounting
- **Requirement**: Bad debt write-off restricted to ADMIN with formal audit trail and balanced ledger entry.
- **Decision**:
  - Endpoint `POST /loans/{id}/write-off` strictly requires role `ADMIN` and a non-empty `reason`.
  - Posts double-entry journal entry:
    - Debit 5010 Bad Debt Expense / Loan Write-offs (for outstanding principal balance)
    - Credit 1100 Member Loans Receivable (for outstanding principal balance)
  - Loan moves to `WRITTEN_OFF` status with actor ID, timestamp, and audit logging.

