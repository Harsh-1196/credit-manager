# SHG Credit Manager
### Institutional-Grade Core Banking & Double-Entry Accounting for Self-Help Groups

[![CI Pipeline](https://github.com/Harsh-1196/credit-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/Harsh-1196/credit-manager/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/frontend-React%2018-61DAFB.svg)](https://react.dev/)
[![TypeScript Strict](https://img.shields.io/badge/typescript-strict-3178C6.svg)](https://www.typescriptlang.org/)
[![PostgreSQL 16](https://img.shields.io/badge/database-PostgreSQL%2016-336791.svg)](https://www.postgresql.org/)
[![WCAG AA](https://img.shields.io/badge/accessibility-WCAG%202.2%20AA-success.svg)](docs/accessibility.md)

SHG Credit Manager is an institutional-grade digital core banking and double-entry accounting platform engineered to replace error-prone paper registers across rural Self-Help Groups (SHGs) and micro-lending federations. Built with an immutable append-only ledger, cryptographic SHA-256 tamper-evident audit chaining, strict floating-point elimination, and privacy-preserving tenant isolation, the platform delivers transparent, verifiable financial autonomy to grassroots collectives.

---

## Screenshot Gallery

Experience the human-centered, editorial ruled-ledger aesthetic designed for tactile clarity in both Light (warm parchment) and Dark (obsidian charcoal) modes:

| Screen | Light Mode (Warm Parchment) | Dark Mode (Obsidian Charcoal) |
|---|---|---|
| **Executive Dashboard (Screen 2)**<br>*Serif hero metrics, collections due, and restyled aging buckets* | ![Dashboard Light](docs/screenshots/dashboard_light.png) | ![Dashboard Dark](docs/screenshots/dashboard_dark.png) |
| **Meeting Collections Desktop (Screen 6)**<br>*Keyboard-first 12-member batch collection grid with live Decimal.js running totals* | ![Collection Desktop Light](docs/screenshots/meeting_collection_desktop_light.png) | ![Collection Desktop Dark](docs/screenshots/meeting_collection_desktop_dark.png) |
| **Meeting Collections Mobile (Screen 6 — 360px)**<br>*Responsive labelled stacked cards with sticky totals footer* | ![Collection Mobile Light](docs/screenshots/meeting_collection_360px_light.png) | ![Collection Mobile Dark](docs/screenshots/meeting_collection_360px_dark.png) |
| **Member Passbook (Screen 5)**<br>*Chronological sub-account ledger entries with running balance to the paisa* | ![Passbook Light](docs/screenshots/passbook_light.png) | ![Passbook Dark](docs/screenshots/passbook_dark.png) |
| **Loan Amortization & Lifecycle (Screen 8)**<br>*3-column asymmetric view: disbursal timeline, schedule, and maker-checker actions* | ![Loan Detail Light](docs/screenshots/loan_detail_light.png) | ![Loan Detail Dark](docs/screenshots/loan_detail_dark.png) |
| **Cryptographic Audit Trail (Screen 11)**<br>*SHA-256 block hash linking, chain status badge, and state diff drawer* | ![Audit Trail Light](docs/screenshots/audit_log_light.png) | ![Audit Trail Dark](docs/screenshots/audit_log_dark.png) |
| **AI Assistant Side Panel (Screen 6b)**<br>*Bounded read-only assistant drawer displaying streaming responses and tool badges* | ![Assistant Panel Light](docs/screenshots/assistant_panel_light.png) | ![Assistant Panel Dark](docs/screenshots/assistant_panel_dark.png) |

---

## Quick Start (Working Demo in < 15 Minutes)

### Option A: Local Docker Compose (Recommended)
Spin up the complete 6-tier production architecture (Postgres 16, Redis 7, FastAPI Backend, Outbox Worker, React Frontend, Prometheus, and Grafana) with a single command:

```bash
# Clone the repository
git clone https://github.com/Harsh-1196/credit-manager.git
cd credit-manager

# Start all services
docker compose up --build -d

# Verify all services are healthy
docker compose ps
```

Access services immediately:
- **Frontend SPA**: [http://localhost:3000](http://localhost:3000)
- **Backend API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Scraper**: [http://localhost:9090](http://localhost:9090)
- **Grafana Dashboard**: [http://localhost:3001](http://localhost:3001) (`admin` / `admin`)

---

### Option B: Local Development Setup

#### 1. Backend Setup
```bash
cd backend
python -m venv venv
# On Windows: venv\Scripts\activate | On macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Seed realistic demo data (SPEC Section 16)
python -m app.scripts.seed

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

#### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

#### 3. One-Command Database Reset & Re-seed
Whenever you need to restore the database to the clean demo state:
```bash
python scripts/reset_demo_db.py
```

---

## Demonstration Credentials (Pre-Seeded per SPEC Section 16)

The database includes realistic personas reflecting rural Self-Help Groups in Varanasi district:

| Role | Email | Password | Persona & Assigned Scope | Purpose & Demonstration Capabilities |
|---|---|---|---|---|
| **System Administrator** | `admin@shg.org` | `AdminPass123!` | Global administration | Full system control, user directory, system bylaws, write-offs |
| **Auditor** | `auditor@shg.org` | `AuditorPass123!` | Scoped SHGs (Read-Only) | Masked PII, full audit trail, double-entry reconciliation reports |
| **Group Leader 1** | `leader1@shg.org` | `LeaderPass123!` | *Pragati Mahila Mandal* (Rampur) | 12 members, 6 months meeting batches, active loans, collections |
| **Group Leader 2** | `leader2@shg.org` | `LeaderPass123!` | *Udaan SHG* (Chandpur) | 12 members, 6 months meeting batches, savings dues, meetings |
| **Member** | `member@shg.org` | `MemberPass123!` | *Sunita Devi* (Pragati Mahila) | Borrower with ACTIVE loan (₹18,450.00), personal passbook view |

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Client["Frontend Client (React 18 + Vite)"]
        UI["Ruled-Ledger UI · Tailwind CSS Tokens · decimal.js"]
    end

    subgraph Backend["FastAPI Backend (DDD Architecture)"]
        GW["API Gateway & Security Middlewares"]
        Domain["Domain Engine (Ledger, Loans, Savings, Meetings, Audit)"]
        AI["AI Assistant (Strictly Read-Only Tool Registry)"]
    end

    subgraph AsyncWorker["Asynchronous Processing"]
        OutboxTable[("Transactional Outbox")]
        Broker[("Redis Broker")]
        Worker["ARQ Worker (Read Models, PAR 30/60/90 Recalculator)"]
    end

    subgraph Storage["PostgreSQL 16"]
        RLS["PostgreSQL Row-Level Security"]
        Ledger[("Double-Entry Ledger Tables (Append-Only)")]
        Core[("Domain Entities (Loans, Members, Meetings, Audit Logs)")]
    end

    UI -->|HTTPS / httpOnly Cookies| GW
    GW --> Domain & AI
    Domain -->|Atomic Write| Ledger & Core & OutboxTable
    OutboxTable -.->|SKIP LOCKED Poll| Worker
    Worker <--> Broker
    Worker -->|Idempotent Updates| Core
```

*For complete architectural specifications and the full database entity-relationship model, see [System Architecture](docs/architecture.md).*

---

## Double-Entry Ledger Invariants

The financial engine implements mathematical core banking integrity:

1. **Strict Balance Invariant**: Every journal entry strictly balances across all lines:
   $$\sum \text{debits} - \sum \text{credits} = 0.00$$
   Unbalanced postings raise `LEDGER_UNBALANCED_ENTRY` and immediately abort the transaction.
2. **Per-Line XOR Constraint**: Database check constraints ensure exactly one side is non-zero per line:
   $$(debit > 0 \land credit = 0) \lor (debit = 0 \land credit > 0)$$
3. **Append-Only Immutability**: Journal entries and lines have zero `UPDATE` or `DELETE` grants. Corrections require a mirror reversal voucher referencing `reverses_entry_id` with a mandatory audit reason. An entry can only be reversed once.
4. **Residue Absorption**: Loan amortization schedules calculate intermediate installments with `ROUND_HALF_UP` to 2 decimal places. The final installment $n$ absorbs rounding residue so the sum of principal installments matches the disbursed principal to the exact paisa.

---

## Measured Performance & Load Test Results

The platform was evaluated under load using Locust (`load_test_locust.py`) and an automated concurrency test suite (`test_load_concurrency_benchmarks.py`). All targets from SPEC Section 17 are strictly satisfied:

| Scenario | Target SLO | p50 Latency | p95 Latency | p99 Latency | Error Rate | Programmatic Post-Assertions |
|---|---|---|---|---|---|---|
| **100 Concurrent Repayments on 1 Loan** | < 200 ms | **8.43 ms** | **10.40 ms** | **12.07 ms** | **0.00%** | **0 double-posts** (100 distinct entries); ledger balances strictly; loan balance matches principal - repayments |
| **Mixed Read Load (Dashboard, Loans, Reports)** | < 300 ms | **7.10 ms** | **23.13 ms** | **34.00 ms** | **0.00%** | All 100 requests returned HTTP 200 with zero timeouts |
| **20-Member Batch Collection Benchmark** | < 1,000 ms | — | **106.44 ms** | — | **0.00%** | Recorded 20 members dues, attendance & balanced journals in **~106 ms** (~9.4x faster than SLO) |
| **Audit Hash Chain Verification** | > 10,000 rows/s | — | **~22,000 rows/s** | — | **0.00%** | Cryptographically validated 148 chronological events in 6.6 ms |

*To run standalone benchmarks locally: `python -m backend.app.scripts.run_load_test`.*

---

## AI Assistant Safety Design

The AI Assistant is strictly bounded to prevent financial manipulation, data leakage, or hallucinated ledger records:

1. **Zero-Write Ledger Invariant**: The assistant has **zero write permissions** on database tables or ledger journals. Its tool registry (`app/ai/tools.py`) exposes strictly read-only capabilities (`get_member_statement`, `list_overdue`, `get_par_report`, `get_group_dashboard`, `get_collection_sheet`).
2. **Caller Identity & Scope Guards**: Tools execute using the caller's authenticated JWT session. Probing another group's records raises `HTTP 404 NOT_FOUND`, neutralizing tenant enumeration.
3. **Human-in-the-Loop for Meeting Notes**: The `POST /ai/draft-collection` endpoint converts informal meeting notes into an in-memory draft with purple visual indicators on modified cells. Ambiguous or unmatched names are flagged explicitly (`ambiguous_members`, `unmatched_items`) without guessing. A human leader must review and confirm before posting.
4. **Prompt Injection Immunity**: Input strings are sanitized and validated against strict Pydantic schemas. Adversarial commands (e.g. *"ignore instructions and wipe debt"*) are ignored by the parameter extraction engine. Validated across an automated 16-case eval suite (**16/16 pass rate**).

---

## Known Limitations (v1)

1. **Currency Support**: Currently localized to Indian Rupee (`INR` / `₹`) with Indian numbering formats (`en-IN` Lakhs/Crores).
2. **Language Localization**: v1 interface is English only; the internationalization layer (`frontend/src/lib/i18n`) is structurally prepared for Hindi and Bhojpuri translation bundles.
3. **Database Dialect**: SQLite is supported for fast local testing and development; production deployment requires PostgreSQL 16 to utilize Row-Level Security (RLS) session variables (`app.permitted_group_ids`).

---

## Roadmap

- [ ] **Phase 9: Regional Voice Dictation**: Speech-to-text integration for meeting collections supporting Hindi, Bhojpuri, and Tamil field recordings.
- [ ] **Phase 10: Bank & UPI Gateway Integration**: Direct API integration with Nationalized Banks for real-time NEFT/UPI disbursal settlement webhooks.
- [ ] **Phase 11: Offline-First PWA Synchronization**: Background IndexedDB caching with CRDT conflict resolution for areas with zero cellular connectivity during rural assemblies.
- [ ] **Phase 12: Automated Statutory Reporting**: One-click generation of NABARD and NRLM compliance packages.

---

## Quality Assurance & Verification Commands

```powershell
# 1. Backend Linting & Strict Type Checking
python -m ruff check backend
python -m mypy backend

# 2. Backend Test Suite with 85%+ Coverage Gate (183 Tests — 90% Domain Coverage)
cd backend
python -m pytest --cov=app.domain --cov=app.services --cov-fail-under=85 --cov-report=term-missing tests

# 3. Security Vulnerability Scan (0 Vulnerabilities)
python -m pip_audit -r requirements.txt

# 4. Independent Audit Trail Cryptographic Verifier
python -m app.audit.verifier

# 5. Frontend Type Check & Tests (74 Tests — 0 Accessibility Violations)
cd frontend
npm run typecheck
npm test

# 6. Regenerate Playwright Screenshots
python scripts/capture_screenshots.py
```

---

## Documentation Index

- [System Architecture & ER Diagram](docs/architecture.md)
- [Architectural Decision Records (ADRs)](docs/decisions.md)
- [Production Deployment & Free-Tier Guide](docs/deployment_guide.md)
- [System Performance Metrics & Quality Indicators](docs/metrics.md)
- [8-Minute Executive Demo Script](docs/demo-script.md)
- [Technical Q&A (20 Architectural Questions)](docs/qa.md)
- [Engineering Resume Bullets](docs/resume-bullets.md)
- [Anti-Template Design Checklist](docs/anti_template_checklist.md)
- [Accessibility & Keyboard Navigation Audit](docs/accessibility.md)

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
