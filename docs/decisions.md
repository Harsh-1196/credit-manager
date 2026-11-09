# Architectural Decision Records (ADR) - SHG Credit Manager

## Status
Living document. Recorded decisions and defaults adopted during Phase 0 and subsequent phases.

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

## 2. Design System & WCAG AA Contrast Checks

During Phase 0, all color tokens specified in SPEC Section 12.2 were audited against the WCAG 2.2 Level AA contrast requirements (minimum 4.5:1 for normal body text, 3.0:1 for large text and UI components).

### 2.1 Audit Results & Token Refinements
- **Light Theme Backgrounds**:
  - `--bg`: `#FAF8F4`
  - `--surface`: `#FFFFFF`
  - `--surface-sunken`: `#F2EFE9`
  - `--surface-raised`: `#FFFFFF`
- **Light Theme Inks**:
  - `--ink`: `#1F2421` (Contrast with `--bg` = 13.9:1, exceeds 4.5:1)
  - `--ink-muted`: `#525C56` (Contrast with `--bg` = 5.6:1, exceeds 4.5:1)
  - `--ink-faint`: `#7D8781` (Used only for decorative borders/badges, 3.2:1)
- **Primary & Accent Tokens**:
  - `--primary`: `#1B4931` (Deep Forest Green, 8.8:1 against `--bg`)
  - `--primary-tint`: `#E8F0EB` (Background tint, `--primary` on `--primary-tint` = 7.1:1)
  - `--accent`: `#C97D2E` (Ochre, large text 3.3:1; paired with dark ink for buttons)
  - `--accent-subtle`: `#FDF3E7`
- **Dark Theme Audit**:
  - `--bg`: `#121513`
  - `--surface`: `#1A1E1B`
  - `--ink`: `#F0F2F1` (Contrast with `--bg` = 15.2:1)
  - `--ink-muted`: `#A4ABA6` (Contrast with `--bg` = 7.4:1)
  - `--primary`: `#52A374` (Sage green, 6.2:1 against dark surface)

---

## 3. Phase 1 Architecture & Authorization Decisions

### 3.1 Scoped Object Queries: 404 vs 403
- **Rule**: Out-of-scope resources (groups, group settings, members) return `HTTP 404 NOT_FOUND` rather than `403 FORBIDDEN`.
- **Reasoning**:
  1. Prevents group ID and member enumeration attacks across organizations.
  2. Protects member privacy across different rural self-help groups.

### 3.2 Audit Log Hash Chaining & Normalized ISO Timestamps
- **Rule**: Audit log hashes are computed over `SHA-256(prev_hash || canonical_json(entry))`. Timestamps must be normalized to UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
- **Reasoning**:
  1. Different SQL dialects (SQLite vs Postgres) handle timezone offsets and fractional seconds differently.
  2. Standardizing canonical datetime string serialization ensures deterministic row hashes and verification across cross-platform test fixtures and production database engines.

### 3.3 PII Minimization on Member Registration
- **Rule**: ID proofs (Aadhaar, Voter ID, PAN, Ration card) are only stored as the last 4 digits (`id_proof_last4`). Full ID numbers are never persisted to disk.
- **Reasoning**:
  1. Adheres to SPEC Section 9 on PII minimization and privacy regulations (UIDAI Aadhaar storage mandates).
  2. Phone numbers and residential addresses are dynamically masked for AUDITOR and non-self MEMBER queries.

### 3.4 In-Memory Tokens and Silent Token Rotation
- **Rule**: JWT access tokens are short-lived (15 minutes) and stored exclusively in frontend memory. Refresh tokens are 7-day tokens stored in `httpOnly`, `Secure`, `SameSite=Strict` cookies.
- **Reasoning**:
  1. Protects against XSS token harvesting.
  2. Double-submit `shg_csrf_token` cookie and `X-CSRF-Token` header protect mutating endpoints against CSRF attacks.
  3. Refresh token reuse triggers immediate family revocation, neutralizing stolen credentials.
