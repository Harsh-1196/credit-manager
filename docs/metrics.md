# Metrics & Quality Indicators - SHG Credit Manager

This document tracks system health, operational SLOs, code coverage, and quality benchmarks for the SHG Credit Manager.

---

## 1. System Performance SLOs (from SPEC Section 17)

| Metric | Target | Measurement Method | Status |
|---|---|---|---|
| List Endpoints p95 Latency | < 300 ms | Middleware request timer & Prometheus/APM | Baseline established (< 20ms local) |
| Meeting Collections Batch (20 members) | < 1,000 ms | Integration load benchmark | Phase 4 target |
| Disbursal / Journal Posting Latency | < 250 ms | Transaction timer | Phase 3 target |
| Audit Row Hash Verification Speed | > 10,000 rows/sec | Verifier benchmark (`app.audit.verifier`) | Verified (~22,000 rows/sec) |

---

## 2. Test Coverage & Code Quality Benchmarks (Phase 2)

| Component | Target Coverage | Tooling | Current Status |
|---|---|---|---|
| Backend Test Suite | 100% core Phase 1 & 2 flows | pytest (38 tests) | **38/38 passing** |
| Backend Linting & Formatting | 0 errors | Ruff | **0 errors, clean** |
| Backend Type Checking | Strict, 0 errors | Mypy strict (66 source files) | **0 errors, clean** |
| Frontend Test Suite | Core money, auth, passbook, savings | Vitest + RTL (23 tests) | **23/23 passing** |
| Frontend Type Checking | Strict, 0 errors | TypeScript (`tsc --noEmit`) | **0 errors, clean** |
| Frontend Production Build | Zero bundle warnings | Vite 5.x build | **Built successfully** |
| Contrast Accessibility | 100% WCAG AA | WCAG 2.2 Relative Luminance Audit | Verified in `docs/decisions.md` |

### Detailed Test Inventory:
- **Backend (38 tests)**:
  - `test_ledger.py` & `test_ledger_properties.py` (8 tests):
    - Balanced double-entry posting (`sum(debit) == sum(credit)`).
    - Unbalanced journal entry rejection (`LEDGER_UNBALANCED_ENTRY`).
    - Debit XOR credit line side constraint (`LEDGER_INVALID_LINE_SIDE`).
    - Mirror reversal entry creation with `reverses_entry_id` link.
    - Double reversal rejection (`ENTRY_ALREADY_REVERSED`) and cannot reverse a reversal (`CANNOT_REVERSE_REVERSAL`).
    - Ledger append-only database & ORM level immutability (prohibition of UPDATE and DELETE).
    - **Hypothesis property tests** running 25 random sequences of deposits, withdrawals, fines and reversals: every journal entry balances individually and overall ledger trial balance `sum(debit) == sum(credit)`.
  - `test_savings.py` (5 tests):
    - Dues generation per active member per period without duplication.
    - Late fine calculation with grace period (5 days) and 100% monthly dues cap.
    - Savings collection posting balanced journal entries and updating dues to PAID.
    - Savings withdrawal enforcing sufficient savings balance.
    - Idempotency replay returns identical cached response without double-posting; conflicting request payload returns 409 Conflict.
    - Passbook API endpoint displaying ruled-ledger columns and ADMIN reversal flow restoring net zero balance.
  - `test_auth.py` (8 tests): login success, invalid credentials, lockout after 5 failures (15 min cooldown), refresh token rotation, token family revocation upon replay/reuse detection, logout revocation, `/auth/me` with group scoping, change-password.
  - `test_authorization.py` (7 tests): parametrized role matrix (ADMIN, GROUP_LEADER, AUDITOR, MEMBER) for users, groups, settings, member enrollment; cross-group access returning 404 (not 403); PII masking of phone and address for AUDITOR and non-self MEMBER.
  - `test_audit.py` (2 tests): mutation writes audit log with SHA-256 hash chaining; tampering detection by `verify_audit_chain` detecting first compromised link.
  - `test_health.py` (5 tests): `/health` liveness, `/ready` database readiness, request ID propagation, uniform error response format.
  - `test_money.py` (3 tests): quantize Decimal(14,2), rejection of floating-point numbers, Indian currency serialization.
- **Frontend (23 tests)**:
  - `MemberPassbookTab.test.tsx` (3 tests): ruled-ledger layout with separate positive Debit and Credit columns (never signed), date range filter, ADMIN-only reversal button.
  - `RecordSavingsModal.test.tsx` (2 tests): two-step record savings workflow with review and confirmation restating member name and amount; client-side UUID idempotency key to prevent double submits.
  - `MoneyText.test.tsx` (11 tests): Indian numeral grouping (en-IN), lakh/crore formatting, negative cue, overdue styling with text cue.
  - `LoginPage.test.tsx` (3 tests): editorial login layout, inline validation for email/password, account lockout alert handling.
  - `SidebarRoleScoping.test.tsx` (4 tests): role-aware UI navigation check for ADMIN, GROUP_LEADER, AUDITOR, and MEMBER.

---

## 3. Operational & Domain Invariants

| Invariant | Target | Verification Method | Status |
|---|---|---|---|
| Double-entry Balance | Every entry `sum(debit) == sum(credit)` | Database constraint & posting service | Enforced & verified by Hypothesis |
| Ledger Immutability | Append-only (no UPDATE or DELETE) | Database triggers & ORM event listeners | Enforced & verified |
| Single Reversal | An entry can only be reversed once | Unique constraint `reverses_entry_id` & domain check | Enforced & verified |
| Ruled-Ledger Formatting | Debits/Credits separate, never signed | Passbook UI & serializer | Enforced & verified |
| Client Idempotency | Double-click cannot double-post | Client UUID key + Server cache/conflict | Enforced & verified |
| Scoped Object Queries | Return 404 for out-of-scope objects | Security test suite & API dependencies | Verified (never leaks 403) |
| ID Proof Protection | Store last 4 digits only | API validation schema & DB column | Enforced (`id_proof_last4`) |
| PII Masking | Mask phone and address for Auditor / Members | Domain masking service | Enforced & verified |
| Audit Tamper Resistance | 100% unbroken SHA-256 chain | `python -m app.scripts.verify_audit_chain` | Enforced & verified |
| Floating-point Money Violations | 0 occurrences | Strict Decimal checks & lint | Enforced |
