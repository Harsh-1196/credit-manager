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

## 2. Test Coverage & Code Quality Benchmarks (Phase 1)

| Component | Target Coverage | Tooling | Current Status |
|---|---|---|---|
| Backend Test Suite | 100% core Phase 1 flows | pytest (25 tests) | **25/25 passing** |
| Backend Linting & Formatting | 0 errors | Ruff | **0 errors, clean** |
| Backend Type Checking | Strict, 0 errors | Mypy strict (48 source files) | **0 errors, clean** |
| Frontend Test Suite | Core money, auth, role-scoping | Vitest + RTL (18 tests) | **18/18 passing** |
| Frontend Type Checking | Strict, 0 errors | TypeScript (`tsc --noEmit`) | **0 errors, clean** |
| Frontend Production Build | Zero bundle warnings | Vite 5.x build | **Built (482 kB JS, 23 kB CSS)** |
| Contrast Accessibility | 100% WCAG AA | WCAG 2.2 Relative Luminance Audit | Verified in `docs/decisions.md` |

### Detailed Test Inventory:
- **Backend (25 tests)**:
  - `test_auth.py` (8 tests): login success, invalid credentials, lockout after 5 failures (15 min cooldown), refresh token rotation, token family revocation upon replay/reuse detection, logout revocation, `/auth/me` with group scoping, change-password.
  - `test_authorization.py` (7 tests): parametrized role matrix (ADMIN, GROUP_LEADER, AUDITOR, MEMBER) for users, groups, settings, member enrollment; cross-group access returning 404 (not 403); PII masking of phone and address for AUDITOR and non-self MEMBER.
  - `test_audit.py` (2 tests): mutation writes audit log with SHA-256 hash chaining; tampering detection by `verify_audit_chain` detecting first compromised link.
  - `test_health.py` (5 tests): `/health` liveness, `/ready` database readiness, request ID propagation, uniform error response format.
  - `test_money.py` (3 tests): quantize Decimal(14,2), rejection of floating-point numbers, Indian currency serialization.
- **Frontend (18 tests)**:
  - `MoneyText.test.tsx` (11 tests): Indian numeral grouping (en-IN), lakh/crore formatting, negative cue, overdue styling with text cue.
  - `LoginPage.test.tsx` (3 tests): editorial login layout, inline validation for email/password, account lockout alert handling.
  - `SidebarRoleScoping.test.tsx` (4 tests): role-aware UI navigation check for ADMIN, GROUP_LEADER, AUDITOR, and MEMBER.

---

## 3. Operational & Domain Invariants

| Invariant | Target | Verification Method | Status |
|---|---|---|---|
| Scoped Object Queries | Return 404 for out-of-scope objects | Security test suite & API dependencies | Verified (never leaks 403) |
| ID Proof Protection | Store last 4 digits only | API validation schema & DB column | Enforced (`id_proof_last4`) |
| PII Masking | Mask phone and address for Auditor / Members | Domain masking service | Enforced & verified |
| Audit Tamper Resistance | 100% unbroken SHA-256 chain | `python -m app.audit.verifier` | Enforced & verified |
| Refresh Token Reuse Detection | Revoke token family on reuse | Auth service & test suite | Enforced & verified |
| Floating-point Money Violations | 0 occurrences | Strict Decimal checks & lint | Enforced |
