# SPEC: SHG Credit Manager

Micro-lending / Self-Help Group Credit Management System

Version 1.0 · Source of truth for the build. Referenced by `prompt.md`.

---

## 1. Goals and scope

**Goal:** Replace paper notebooks used by Self-Help Groups with an accurate, secure, auditable digital system for savings, internal lending, and reporting.

**In scope**

- Group and member management
- Meetings, savings collection, fines
- Loan lifecycle: application, approval, disbursal, repayment, closure, write-off
- Double-entry ledger, passbooks, reports
- Role-based access, audit trail

**Out of scope for v1**

- Real payment gateway or UPI integration (payments are recorded manually by the leader)
- SMS/WhatsApp notifications (design hooks only)
- Bank-linkage loan workflows beyond recording a group-level external loan
- Hindi UI (strings go through an i18n layer so it can be added later)

---

## 2. Roles and permissions

| Role | Scope | Summary |
|---|---|---|
| `ADMIN` | Organization-wide | Manage groups, users, system config; view everything |
| `GROUP_LEADER` | One or more assigned groups | Run meetings, record savings and repayments, approve loans (maker-checker applies) |
| `MEMBER` | Self only | View own passbook, loans, schedule; submit loan application |
| `AUDITOR` | Assigned groups, read-only | View data, reports, and audit log; export |

### Permission matrix

`R` read, `W` write, `A` approve, `-` none. "Own" means the user's own records. "Assigned" means groups the user is attached to.

| Resource | ADMIN | GROUP_LEADER | MEMBER | AUDITOR |
|---|---|---|---|---|
| Users | RW | - | own R | - |
| Groups | RW | assigned R, limited W | own group R | assigned R |
| Group members | RW | assigned RW | own R | assigned R |
| Meetings | R | assigned RW | own group R | assigned R |
| Savings entries | R | assigned RW | own R | assigned R |
| Loan applications | R | assigned RWA* | own RW (create/submit) | assigned R |
| Loan disbursal | - | assigned W | - | - |
| Repayments | R | assigned RW | own R | assigned R |
| Ledger / journal | R | assigned R | own passbook R | assigned R |
| Reports | RW | assigned R | own statement R | assigned R |
| Audit log | R | - | - | assigned R |
| Reversals | W (with reason) | - | - | - |

\* Maker-checker: a leader cannot approve a loan they themselves created or applied for as a member. A second authorized approver is required (another office-bearer, or ADMIN).

**Object-level rule:** every query on group-scoped data must filter by the caller's permitted group IDs. Return `404` (not `403`) for objects outside the caller's scope to avoid leaking existence.

---

## 3. Domain glossary

| Term | Meaning |
|---|---|
| SHG | Self-Help Group |
| Corpus | The group's pooled funds (savings + retained interest + fees/fines) |
| Passbook | Per-member ledger of savings, loans, and repayments |
| Meeting | A scheduled group gathering where collections happen |
| Arrears | Savings or EMIs due but unpaid |
| Disbursal | Releasing an approved loan amount to the member |
| PAR | Portfolio at Risk (30/60/90 days past due) |

---

## 4. Data model

All tables have `id` (UUID), `created_at`, `updated_at`. Money columns are `NUMERIC(14,2)`. Rates are `NUMERIC(6,3)` (percent). Soft-delete via `deleted_at` where noted; **ledger and audit tables are never modified or deleted.**

### 4.1 Identity and access

**users**: `email` (unique, citext), `phone`, `password_hash` (argon2), `role`, `is_active`, `failed_login_count`, `locked_until`, `last_login_at`

**refresh_tokens**: `user_id`, `token_hash`, `family_id`, `expires_at`, `revoked_at`, `replaced_by` (for rotation and reuse detection)

**user_group_access**: `user_id`, `group_id`, `access_level`. Links leaders and auditors to groups.

### 4.2 Groups and members

**shgs**: `name`, `village`, `ward`, `district`, `formation_date`, `meeting_day`, `meeting_frequency`, `bank_account_label`, `status` (`ACTIVE`, `DORMANT`, `CLOSED`)

**group_settings** (1:1 with shgs): `monthly_saving_amount`, `late_fine_per_day`, `fine_grace_days`, `default_interest_rate`, `interest_type` (`FLAT`, `REDUCING`), `max_loan_multiple` (loan cap as multiple of member savings), `min_tenure_months`, `max_tenure_months`, `processing_fee_percent`, `penalty_interest_rate`

**members**: `shg_id`, `user_id` (nullable), `full_name`, `phone`, `address`, `id_proof_type`, `id_proof_last4` (never the full number), `date_of_birth`, `joined_on`, `exited_on`, `status`, `deleted_at`

**member_roles**: `member_id`, `role` (`PRESIDENT`, `SECRETARY`, `TREASURER`, `MEMBER`), `from_date`, `to_date`

### 4.3 Meetings and savings

**meetings**: `shg_id`, `meeting_date`, `status` (`SCHEDULED`, `HELD`, `CANCELLED`), `agenda`, `minutes`, `recorded_by`

**attendance**: `meeting_id`, `member_id`, `status` (`PRESENT`, `ABSENT`, `EXCUSED`)

**savings_dues**: `member_id`, `period` (YYYY-MM), `amount_due`, `amount_paid`, `status` (`PENDING`, `PARTIAL`, `PAID`, `OVERDUE`)

### 4.4 Loans

**loans**: `shg_id`, `member_id`, `loan_number` (human readable, per group sequence), `purpose`, `principal`, `interest_rate`, `interest_type`, `tenure_months`, `processing_fee`, `status`, `applied_by`, `applied_at`, `approved_by`, `approved_at`, `rejection_reason`, `disbursed_at`, `first_due_date`, `closed_at`, `version` (optimistic locking)

**loan_schedule**: `loan_id`, `installment_no`, `due_date`, `principal_due`, `interest_due`, `total_due`, `principal_paid`, `interest_paid`, `penalty_paid`, `status` (`PENDING`, `PARTIAL`, `PAID`, `OVERDUE`)

**loan_status_history**: `loan_id`, `from_status`, `to_status`, `actor_id`, `reason`, `at` (append-only)

**repayments**: `loan_id`, `meeting_id` (nullable), `amount`, `principal_component`, `interest_component`, `penalty_component`, `paid_on`, `mode` (`CASH`, `UPI`, `BANK`), `reference`, `recorded_by`, `journal_entry_id`

### 4.5 Ledger (append-only)

**accounts** (chart of accounts, per group): `shg_id`, `code`, `name`, `type` (`ASSET`, `LIABILITY`, `EQUITY`, `INCOME`, `EXPENSE`), `member_id` (nullable, for member-specific sub-accounts)

**journal_entries**: `shg_id`, `entry_date`, `description`, `source_type` (`SAVINGS`, `DISBURSAL`, `REPAYMENT`, `FINE`, `FEE`, `REVERSAL`, `ADJUSTMENT`), `source_id`, `reverses_entry_id` (nullable), `idempotency_key` (unique per shg), `posted_by`, `posted_at`

**journal_lines**: `entry_id`, `account_id`, `debit` (>= 0), `credit` (>= 0), check constraint that exactly one of debit/credit is non-zero

**Invariants (enforce in DB where possible, always in code):**

- For every `journal_entry`: `SUM(debit) = SUM(credit)`
- Ledger tables have no `UPDATE`/`DELETE` privileges for the app role (use DB triggers or revoked grants)
- A reversed entry can only be reversed once

### 4.6 Platform tables

**audit_log**: `id`, `occurred_at`, `actor_id`, `actor_role`, `ip`, `user_agent`, `request_id`, `action`, `entity_type`, `entity_id`, `before` (JSONB), `after` (JSONB), `prev_hash`, `row_hash` (SHA-256 chain for tamper evidence)

**idempotency_keys**: `key`, `scope`, `request_hash`, `response_status`, `response_body`, `created_at`, `expires_at`

---

## 5. Chart of accounts (per SHG)

| Code | Account | Type |
|---|---|---|
| 1000 | Cash in Hand | ASSET |
| 1010 | Bank Balance | ASSET |
| 1100 | Member Loans Receivable (sub-account per member) | ASSET |
| 1110 | Interest Receivable | ASSET |
| 2000 | Member Savings (sub-account per member) | LIABILITY |
| 2100 | External / Bank Linkage Loan | LIABILITY |
| 3000 | Group Corpus / Retained Surplus | EQUITY |
| 4000 | Interest Income | INCOME |
| 4010 | Fine and Penalty Income | INCOME |
| 4020 | Processing Fee Income | INCOME |
| 5000 | Operating Expenses | EXPENSE |
| 5010 | Loan Write-offs | EXPENSE |

### Posting rules

| Event | Debit | Credit |
|---|---|---|
| Savings collected | Cash (1000) | Member Savings (2000, member) |
| Savings withdrawn | Member Savings (2000, member) | Cash (1000) |
| Loan disbursed | Loans Receivable (1100, member) | Cash (1000) |
| Processing fee charged | Cash (1000) | Processing Fee Income (4020) |
| Repayment: principal | Cash (1000) | Loans Receivable (1100, member) |
| Repayment: interest | Cash (1000) | Interest Income (4000) |
| Fine or penalty | Cash (1000) | Fine and Penalty Income (4010) |
| Loan written off | Loan Write-offs (5010) | Loans Receivable (1100, member) |
| Reversal | Mirror of the original entry (swap debit/credit), `reverses_entry_id` set | |

A single repayment posts **one journal entry with multiple lines** (cash in, principal, interest, penalty) so it is atomic and balanced.

---

## 6. Loan lifecycle

### 6.1 State machine

```
DRAFT -> SUBMITTED -> APPROVED -> DISBURSED -> ACTIVE -> CLOSED
            |             |                       |
            v             v                       v
         REJECTED      REJECTED               OVERDUE -> ACTIVE (when cured)
                                                  |
                                                  v
                                             WRITTEN_OFF
```

| From | To | Who | Conditions |
|---|---|---|---|
| DRAFT | SUBMITTED | applicant or leader | Eligibility checks pass |
| SUBMITTED | APPROVED | approver (not the maker) | Reason optional, decision logged |
| SUBMITTED | REJECTED | approver | Reason required |
| APPROVED | DISBURSED | leader | Group has sufficient cash; posts ledger entry |
| DISBURSED | ACTIVE | system | Schedule generated on disbursal |
| ACTIVE | OVERDUE | system (daily job) | Any installment past due beyond grace |
| OVERDUE | ACTIVE | system | All overdue amounts cleared |
| ACTIVE / OVERDUE | CLOSED | system | Outstanding principal, interest, penalty all zero |
| OVERDUE | WRITTEN_OFF | ADMIN | Reason required; posts write-off entry |

All transitions go through `LoanStateMachine.transition(loan, to_status, actor, reason)`. Every transition writes `loan_status_history` and an audit row.

### 6.2 Eligibility checks (at submission)

- Member is active in the group
- No more than N concurrent active loans (configurable, default 1)
- Requested principal <= `max_loan_multiple` x member's current savings balance
- Requested principal <= available group cash (warning, not a hard block, for approver to see)
- Tenure within `min_tenure_months` and `max_tenure_months`
- No overdue installments on existing loans

### 6.3 Schedule calculation

Rounding: every computed amount is rounded `ROUND_HALF_UP` to 2 dp. The **last installment absorbs the rounding residue** so that totals match exactly.

**Flat interest**

```
total_interest = principal * annual_rate/100 * (tenure_months / 12)
installment    = (principal + total_interest) / tenure_months
principal_part = principal / tenure_months
interest_part  = total_interest / tenure_months
```

**Reducing balance (EMI)**

```
r   = annual_rate / 12 / 100
EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)        # if r == 0, EMI = P / n
for each month:
    interest_i  = outstanding * r
    principal_i = EMI - interest_i
    outstanding -= principal_i
```

**Required known-answer tests** (agent must add more): reducing balance, P=50,000, 12% p.a., 12 months gives EMI of 4,442.44; flat, P=10,000, 12% p.a., 10 months gives total interest 1,000.00 and installment 1,100.00.

### 6.4 Repayment allocation

When a payment is recorded, allocate in this order: **penalty, then interest due, then principal due**, oldest installment first. Overpayment beyond the current due is treated as **prepayment** applied to the next installments' principal (configurable per group: reduce tenure or reduce installment; default reduce tenure). Partial payments leave the installment `PARTIAL`.

### 6.5 Penalty

Late penalty accrues daily on the overdue installment amount at `penalty_interest_rate` after `fine_grace_days`. Penalty accrual is computed by the daily job and stored; it is never recomputed retroactively for closed periods.

---

## 7. Savings and fines

- A `savings_dues` row is generated per active member per period.
- Recording a collection posts the ledger entry and updates the due.
- Late fine = `late_fine_per_day` x days late beyond grace, capped by a configurable maximum.
- Members who exit have their savings settled via a withdrawal entry; they cannot be hard-deleted.

---

## 8. API design

Base path `/api/v1`. JSON. OpenAPI generated by FastAPI; the frontend client is generated from it. Pagination: `?page=&page_size=` (max 100) with `{items, total, page, page_size}`. Dates ISO 8601. Money serialized as **strings** (e.g. `"1250.00"`) to avoid float issues in JS.

**Error format (all errors):**

```json
{ "code": "LOAN_INVALID_TRANSITION", "message": "Cannot move loan from CLOSED to APPROVED.", "details": {}, "request_id": "..." }
```

### Endpoints

**Auth**

- `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`
- `POST /auth/change-password`

**Users (ADMIN)**

- `GET/POST /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/deactivate`

**Groups**

- `GET/POST /groups`, `GET/PATCH /groups/{id}`
- `GET/PUT /groups/{id}/settings`
- `GET/POST /groups/{id}/members`, `GET/PATCH /members/{id}`, `POST /members/{id}/exit`

**Meetings**

- `GET/POST /groups/{id}/meetings`, `GET/PATCH /meetings/{id}`
- `PUT /meetings/{id}/attendance`
- `POST /meetings/{id}/collections`: batch endpoint to record savings and repayments for many members at once (atomic, idempotent)

**Savings**

- `GET /members/{id}/savings`, `GET /groups/{id}/savings-dues?period=`
- `POST /savings/collect`, `POST /savings/withdraw`

**Loans**

- `GET/POST /loans`, `GET /loans/{id}`
- `POST /loans/{id}/submit`, `/approve`, `/reject`, `/disburse`, `/write-off`
- `GET /loans/{id}/schedule`, `GET /loans/{id}/history`
- `POST /loans/{id}/repayments`
- `POST /loans/preview-schedule` (no persistence; used by the application form)

**Ledger**

- `GET /groups/{id}/ledger?from=&to=&account=`
- `GET /members/{id}/passbook?from=&to=`
- `POST /ledger/entries/{id}/reverse` (ADMIN, reason required)

**Reports** (`?format=json|csv|pdf`)

- `GET /reports/group-dashboard/{group_id}`
- `GET /reports/member-statement/{member_id}`
- `GET /reports/group-ledger/{group_id}`
- `GET /reports/loan-portfolio/{group_id}` (including PAR 30/60/90)
- `GET /reports/collection-sheet/{meeting_id}`

**Audit**

- `GET /audit-log?actor=&entity_type=&entity_id=&action=&from=&to=` and `GET /audit-log/export`

**System**

- `GET /health`, `GET /ready`

---

## 9. Security requirements

- **Auth:** access token 15 min, refresh token 7 days in an httpOnly, Secure, SameSite=Strict cookie, rotated on every use; reuse of an old refresh token revokes the whole family.
- **Passwords:** argon2id; minimum length 10; breached-password check optional.
- **Brute force:** rate limit login (e.g. 5/min/IP and per account); lock the account for 15 minutes after 5 consecutive failures.
- **CSRF:** double-submit token or custom header required on cookie-authenticated mutating calls.
- **CORS:** explicit allowlist from env.
- **Authorization:** reusable FastAPI dependencies (`require_role`, `require_group_access`); every group-scoped query filtered by permitted group IDs.
- **Input:** Pydantic validation on all inputs; reject unknown fields; max body size.
- **PII:** ID proofs stored as last 4 digits only; phone and address masked for roles that do not need them; logs never contain tokens, passwords, or full PII.
- **Headers:** HSTS, X-Content-Type-Options, frame protections, a strict CSP on the frontend host.
- **Secrets:** from environment only; `.env.example` has placeholders.
- **Dependencies:** pinned versions; `pip-audit` and `npm audit` in the README checklist.

---

## 10. Audit logging

Every mutating request writes an `audit_log` row containing: actor, role, IP, user agent, request ID, action name, entity type and ID, and `before`/`after` JSON snapshots (with PII masked). Rows are hash-chained: `row_hash = SHA256(prev_hash || canonical_json(row))`. Provide a `verify_audit_chain` management command that reports the first broken link. The audit viewer supports filters and CSV export.

---

## 11. Reports and dashboard

**Group dashboard figures:** total corpus, total savings, outstanding principal, interest earned (period), repayment rate (collected / due), overdue amount, next meeting date, collections due at the next meeting.

**Charts:** savings trend (monthly), loan portfolio aging (current, 1-30, 31-60, 61-90, 90+), disbursals vs. repayments by month.

**Collection sheet:** one row per member showing savings due, EMI due, arrears, fines, and the total to collect, designed to be used at the meeting and printed if needed.

**Portfolio at Risk:** `PAR_x = outstanding principal of loans with any installment overdue more than x days / total outstanding principal`.

All report numbers must reconcile with the ledger. Add a test that computes dashboard totals two ways (from domain tables and from journal lines) and asserts they match.

---

## 12. Design system

### 12.1 Principles

Calm, warm, editorial, trustworthy. Information-dense but unhurried. Borders over shadows. Typography does most of the work. The product should look like a considered accounting book, not a SaaS template.

### 12.2 Tokens (define as CSS variables, map to Tailwind theme; components use semantic names only)

**Color: light**

| Token | Value | Use |
|---|---|---|
| `--bg` | `#FAF8F4` | App background |
| `--surface` | `#FFFFFF` | Panels, tables |
| `--surface-sunken` | `#F3EFE8` | Table headers, inputs, wells |
| `--border` | `#E4DED3` | Hairlines |
| `--border-strong` | `#CFC7B8` | Focus-adjacent, dividers |
| `--ink` | `#1F2421` | Primary text |
| `--ink-muted` | `#5E655F` | Secondary text |
| `--ink-faint` | `#8B918A` | Tertiary, placeholders |
| `--primary` | `#2F5D50` | Primary actions, links |
| `--primary-hover` | `#264B41` | |
| `--primary-tint` | `#E6EFEB` | Subtle selected backgrounds |
| `--accent` | `#B5573A` | Sparing emphasis only |
| `--success` | `#3F7A4F` | |
| `--warning` | `#A8741A` | |
| `--danger` | `#A63D2F` | |
| `--info` | `#3C6A8C` | |

**Color: dark.** Design deliberately, do not invert. Suggested start: `--bg #141816`, `--surface #1B201D`, `--surface-sunken #222823`, `--border #2E3530`, `--ink #ECEAE4`, `--primary #6FA593`, `--accent #D98062`. Verify AA contrast for every text/background pair in both themes.

**Typography**

- Display and key figures: **Fraunces** (or Source Serif 4)
- UI text: **Instrument Sans** (or DM Sans)
- Numerals: `font-variant-numeric: tabular-nums` on all money and table numbers
- Scale (px / line-height): 12/16, 14/20, 16/24, 18/28, 22/30, 28/36, 36/44
- Self-host fonts; set `font-display: swap`; provide fallback stacks

**Space, shape, motion**

- 4px spacing grid
- Radius: 4px (inputs, chips), 6px (buttons), 8px (panels). No pill buttons except status chips
- Shadow: none by default; one very subtle shadow allowed for dialogs and popovers
- Motion: 150 to 200ms ease-out for state changes; respect `prefers-reduced-motion`

### 12.3 Component library

Button (primary, secondary, ghost, danger), Input, Textarea, Select, Combobox, DatePicker, Checkbox, Radio, Switch, Table (sortable, sticky header, dense/comfortable toggle, stacked on mobile), StatusChip, Stat, Tabs, Dialog, Drawer, Toast, Tooltip, EmptyState, Skeleton, Breadcrumbs, CommandPalette, MoneyText (handles Indian grouping, negative and overdue styling).

### 12.4 Money formatting

- Format: `₹1,25,000.00` using `Intl.NumberFormat('en-IN')`
- Always 2 decimals in tables and ledgers; abbreviations (e.g. "1.2L") only in dashboard summaries and always with a tooltip showing the full figure
- Right-align and use tabular numerals
- Debits and credits shown in separate columns in ledger views, not as signed numbers
- Negative or overdue values: color **plus** a text cue (e.g. "Overdue 12 days", a leading minus), never color alone

### 12.5 Screens

1. **Login**: simple, editorial, no hero art.
2. **Dashboard** (role-aware): lead with 3 to 4 key figures in the serif face, then "Collections due" list, then aging chart and savings trend. Avoid a wall of equal cards.
3. **Groups list and detail**: members, settings, meeting history.
4. **Members**: list with search and filters; member profile with tabs (Overview, Passbook, Loans, Attendance).
5. **Passbook**: ruled-ledger look. Columns: Date, Particulars, Debit, Credit, Balance.
6. **Meeting collection** (most important screen): fast, keyboard-driven grid for all members (savings, EMI, fines), live running totals, a confirm step that shows the journal summary before posting. Must work on a 360px phone.
7. **Loan application**: form with live schedule preview and eligibility feedback.
8. **Loan detail**: left, state timeline; center, repayment schedule table; right, summary panel and actions available for the current role and state.
9. **Approvals queue**: pending applications with maker-checker clarity.
10. **Reports**: filters, preview, export buttons.
11. **Audit log**: filterable table with before/after diff drawer.
12. **Settings**: group rules, users (ADMIN).
13. **/styleguide**: living documentation of tokens and components (dev only).

### 12.6 UX and accessibility rules

- WCAG 2.2 AA contrast, visible 2px focus ring using `--primary`, full keyboard operation, logical focus order, semantic landmarks, labelled form controls, `aria-live` for toasts and validation
- Inline validation with helper text; one primary action per view
- Destructive and money-posting actions require a confirmation step that restates the amount and the member
- Every data view has loading (skeleton), empty (helpful sentence plus next action), and error (retry) states
- Responsive breakpoints: 360, 640, 1024, 1280. Tables collapse to labelled stacked rows under 640
- All user-facing strings go through an i18n layer (English only for v1)
- Copy tone: calm, specific, domain vocabulary (corpus, passbook, arrears, disbursal). No marketing language

### 12.7 Anti-template checklist (reviewed in Phase 7)

- [ ] No gradients, glass effects, glows, or neon
- [ ] No emoji in the UI
- [ ] No default font stacks visible
- [ ] No uniform grid of identical rounded cards
- [ ] No placeholder text or round-number demo data
- [ ] No decorative icons beside every heading
- [ ] Money is tabular, right-aligned, Indian-grouped
- [ ] Both themes pass contrast checks

---

## 13. Frontend architecture

- Vite + React 18 + TypeScript (strict)
- Routing: React Router with role-guarded routes
- Data: TanStack Query; API client generated from the backend OpenAPI schema
- Forms: React Hook Form + Zod
- State: server state in Query; minimal local UI state; no global store unless justified in `docs/decisions.md`
- Styling: Tailwind with the token layer above; no raw palette classes in components
- Charts: Recharts, fully restyled to tokens (no default colors or tooltips)
- Money handling: values arrive as strings; use a decimal library (e.g. `decimal.js`) for any client-side arithmetic; never `parseFloat` money
- Tests: Vitest + React Testing Library for components; Playwright for 3 critical flows (login, record collection at a meeting, approve and disburse a loan)

```
frontend/src/
  app/            routes, providers, layout
  components/ui/  design system components
  features/       auth, groups, members, meetings, loans, ledger, reports, audit
  lib/            api client, money, dates, i18n
  styles/         tokens.css, fonts.css, globals.css
```

---

## 14. Backend architecture

```
backend/app/
  main.py
  core/        config, security, deps, errors, logging, money, rounding
  db/          base, session, models/, migrations (alembic)
  domain/      loans/ (state_machine, schedule, eligibility, allocation)
               ledger/ (posting, accounts, reversal)
               savings/, meetings/, groups/
  services/    orchestrate domain + DB transactions
  api/v1/      routers, schemas (Pydantic), dependencies
  audit/       middleware, hashing, verifier
  jobs/        daily overdue/penalty accrual (APScheduler or a CLI command)
  tests/       unit/, integration/, security/, concurrency/
```

Principles: thin routers, business rules in `domain/`, transactions managed in `services/`, no business logic in SQL triggers except the ledger append-only guard and balance check.

**Concurrency:** use `SELECT ... FOR UPDATE` on the loan row (and group cash account where relevant) during repayment and disbursal; also use the loan `version` column for optimistic checks in approval flows.

**Idempotency:** middleware or dependency stores `(key, scope, request_hash)`; a repeat with the same key and hash returns the stored response; same key with a different hash returns `409`.

---

## 15. Testing requirements

| Area | Tests |
|---|---|
| Money | Rounding policy, Decimal only, no float leakage in API |
| Schedule | Known-answer cases (flat and reducing), zero-interest, last-installment residue, 1-month tenure |
| Ledger | Always balanced after random sequences; reversal restores balances; no UPDATE/DELETE permitted |
| Loan state machine | All valid transitions pass; every invalid transition raises `LOAN_INVALID_TRANSITION` |
| Maker-checker | Creator cannot approve own application |
| Idempotency | Replay does not double-post; same key different body returns 409 |
| Concurrency | Two simultaneous repayments on one loan yield correct balances and no deadlock |
| Authorization | Full role x endpoint matrix; cross-group access returns 404; member cannot read another member's passbook |
| Auth | Login lockout, refresh rotation, reuse detection, logout revocation |
| Audit | Every mutation writes a row; hash chain verifies; tampering is detected |
| Reports | Dashboard totals equal ledger-derived totals |
| Frontend | MoneyText formatting, form validation, keyboard operation of the collection grid; Playwright critical flows |

Target: backend coverage >= 85% on `domain/` and `services/`.

---

## 16. Seed data

A `python -m app.scripts.seed` command creating:

- 1 ADMIN, 1 AUDITOR, 2 SHGs (each with a leader and about 12 members with realistic Indian names and different villages)
- 6 months of meetings with attendance and monthly savings
- Loans in every state: a few `ACTIVE`, 2 `CLOSED`, 2 `OVERDUE`, 1 `REJECTED`, 1 `SUBMITTED` awaiting approval
- Fines and one reversal entry so those screens are not empty
- Demo logins printed in the README

---

## 17. Non-functional requirements

- **Performance:** p95 under 300 ms for standard list endpoints with seed-scale data; meeting collection batch for 20 members under 1 second
- **Reliability:** all multi-row money operations are atomic
- **Observability:** structured JSON logs with request ID; `/health` and `/ready`
- **Config:** 12-factor, all settings from environment, validated at startup
- **Portability:** `docker compose up` brings up Postgres; documented commands run migrations, seed, backend, and frontend
- **Browser support:** latest two versions of Chrome, Edge, Firefox, Safari; mobile Chrome and Safari

---

## 18. Deliverables checklist

- [ ] Monorepo with `/backend`, `/frontend`, `docker-compose.yml`, `.env.example` (both), root `README.md`
- [ ] Alembic migrations and Mermaid ER diagram in `docs/`
- [ ] Passing backend and frontend test suites
- [ ] Seed script and demo logins
- [ ] `/styleguide` page
- [ ] `docs/decisions.md` listing every assumption made
- [ ] Screenshots of: dashboard, meeting collection, passbook, loan detail, audit log (light and dark)
- [ ] Anti-template checklist (section 12.7) completed with notes

---

## 19. Open decisions (agent should propose a default and record it)

1. Prepayment behavior default: reduce tenure vs. reduce installment (spec default: reduce tenure)
2. Whether interest is accrued daily or recognized per installment (spec default: per installment)
3. PDF generation library for backend (WeasyPrint or ReportLab)
4. Scheduler for the daily job (APScheduler in-process vs. a CLI command run by cron)
