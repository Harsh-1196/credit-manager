# System Architecture & Technical Specifications - SHG Credit Manager

This document provides a comprehensive overview of the system architecture, component boundaries, data persistence model, transactional guarantees, and resilience patterns powering the **SHG Credit Manager**.

---

## 1. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph ClientLayer["Frontend Client Layer (React 18 + Vite SPA)"]
        UI["React 18 PWA (Editorial Ruled-Ledger Design)"]
        State["TanStack React Query + Decimal.js"]
        AIAssistantUI["AI Assistant Side Panel & Notes Modal"]
    end

    subgraph APILayer["API Gateway & Security Layer (FastAPI)"]
        Middlewares["Middlewares (SecurityHeaders, MaxBodySize, RequestContext, Audit)"]
        AuthGuard["Auth & Role Guards (Argon2id, 15m Access JWT, 7d Rotating Refresh)"]
        Endpoints["REST API Endpoints (/loans, /meetings, /savings, /reports, /dashboard)"]
    end

    subgraph DomainLayer["Domain & Financial Engine (DDD)"]
        LedgerEngine["Double-Entry Ledger Engine (Posting, Accounts, Reversals)"]
        LoanEngine["Credit Amortization & Allocation (Reducing EMI, Flat, Waterfall)"]
        BatchEngine["Meeting Batch Collections (All-or-Nothing Atomicity)"]
        ReconEngine["Reconciliation Engine (Ledger vs Read Models)"]
        AuditEngine["Cryptographic Audit Chaining (SHA-256 Verifier)"]
    end

    subgraph AILayer["AI Layer (Strictly Read-Only)"]
        LLMClient["Provider-Agnostic LLM Wrapper (Gemini 2.5 / Mock Fallback)"]
        ToolRegistry["Scoped Read-Only Tool Registry (Zero-Write Invariant)"]
    end

    subgraph OutboxLayer["Asynchronous Outbox & Background Workers"]
        OutboxTable[("outbox_events (Postgres)")]
        RedisBroker[("Redis Broker (Queue)")]
        ARQWorker["ARQ Background Worker"]
        Consumer1["Consumer 1: Dashboard Read Model"]
        Consumer2["Consumer 2: PAR 30/60/90 & Arrears Recalculator"]
        DedupeLog[("outbox_consumer_logs (Idempotent De-duplication)")]
    end

    subgraph DataLayer["Persistence Layer (PostgreSQL 16)"]
        RLS["PostgreSQL Row-Level Security (app.permitted_group_ids)"]
        LedgerTables[("Double-Entry Ledger (accounts, journal_entries, journal_lines)")]
        DomainTables[("Core Banking (loans, loan_schedule, members, meetings)")]
        AuditTables[("Cryptographic Audit Logs (audit_logs SHA-256 chain)")]
        ReadModelTables[("Denormalized Read Models (dashboard_read_models)")]
    end

    %% Interactions
    UI -->|HTTPS / httpOnly Cookies| Middlewares
    Middlewares --> AuthGuard
    AuthGuard --> Endpoints
    Endpoints --> DomainLayer
    Endpoints --> AILayer
    
    AILayer -->|Caller Identity & Scoped Reads| DomainLayer
    
    DomainLayer -->|Atomic Multi-Table Write| DataLayer
    DomainLayer -->|Same-Tx Write| OutboxTable
    
    OutboxTable -.->|SELECT ... FOR UPDATE SKIP LOCKED| ARQWorker
    ARQWorker <--> RedisBroker
    ARQWorker --> Consumer1 & Consumer2
    Consumer1 & Consumer2 --> DedupeLog
    Consumer1 --> ReadModelTables
    Consumer2 --> ReadModelTables

    Endpoints -->|Direct Fast Reads| ReadModelTables
```

---

## 2. Entity-Relationship (ER) Data Model

```mermaid
erDiagram
    users ||--o{ user_group_access : "granted"
    shgs ||--o{ user_group_access : "assigned"
    shgs ||--|| group_settings : "configured_by"
    shgs ||--o{ members : "enrolls"
    shgs ||--o{ accounts : "charts"
    shgs ||--o{ meetings : "schedules"
    shgs ||--o{ loans : "issues"
    shgs ||--o{ journal_entries : "records"
    shgs ||--o{ dashboard_read_models : "aggregates"
    shgs ||--o{ reconciliation_runs : "audits"

    members ||--o{ member_roles : "holds"
    members ||--o{ loans : "borrows"
    members ||--o{ savings_dues : "owes"
    members ||--o{ attendance : "attends"

    accounts ||--o{ journal_lines : "contains"
    journal_entries ||--o{ journal_lines : "balances"
    journal_entries |o--o| journal_entries : "reverses"

    loans ||--o{ loan_schedule : "schedules"
    loans ||--o{ loan_status_history : "tracks"
    loans ||--o{ journal_entries : "generates"

    meetings ||--o{ attendance : "logs"

    users {
        uuid id PK
        string email UK
        string phone
        string password_hash
        string role
        boolean is_active
        int failed_login_count
        timestamp locked_until
    }

    shgs {
        uuid id PK
        string name
        string village
        string ward
        string district
        date formation_date
        string meeting_day
        string meeting_frequency
        string bank_account_label
        string status
    }

    group_settings {
        uuid id PK
        uuid shg_id FK
        numeric monthly_saving_amount
        numeric late_fine_per_day
        int fine_grace_days
        numeric default_interest_rate
        string interest_type
        numeric max_loan_multiple
        int min_tenure_months
        int max_tenure_months
        numeric processing_fee_percent
        numeric penalty_interest_rate
    }

    members {
        uuid id PK
        uuid shg_id FK
        string full_name
        string phone
        string gender
        string id_proof_type
        string id_proof_last4
        date joined_on
        string status
        date exit_date
    }

    accounts {
        uuid id PK
        uuid shg_id FK
        string code
        string name
        string account_type
        uuid member_id FK
        boolean is_active
    }

    journal_entries {
        uuid id PK
        uuid shg_id FK
        date entry_date
        string description
        string source_type
        uuid source_id
        uuid posted_by FK
        uuid reverses_entry_id FK
        string idempotency_key UK
    }

    journal_lines {
        uuid id PK
        uuid entry_id FK
        uuid account_id FK
        numeric debit
        numeric credit
        string description
    }

    loans {
        uuid id PK
        uuid shg_id FK
        uuid member_id FK
        string loan_number
        string purpose
        numeric principal
        numeric interest_rate
        string interest_type
        int tenure_months
        numeric processing_fee
        string status
        int version
        uuid applied_by FK
        uuid approved_by FK
        uuid disbursed_by FK
        date first_due_date
    }

    loan_schedule {
        uuid id PK
        uuid loan_id FK
        int installment_no
        date due_date
        numeric principal_due
        numeric interest_due
        numeric total_due
        numeric principal_paid
        numeric interest_paid
        numeric penalty_due
        numeric penalty_paid
        string status
        date last_penalty_accrual_date
    }

    meetings {
        uuid id PK
        uuid shg_id FK
        date meeting_date
        string status
        string agenda
        string minutes
    }

    attendance {
        uuid id PK
        uuid meeting_id FK
        uuid member_id FK
        string status
    }

    savings_dues {
        uuid id PK
        uuid shg_id FK
        uuid member_id FK
        string period
        numeric due_amount
        numeric paid_amount
        string status
        numeric fine_amount
        numeric fine_paid
    }

    outbox_events {
        uuid id PK
        uuid shg_id FK
        string event_type
        string aggregate_type
        uuid aggregate_id
        json payload
        string status
        int attempts
        timestamp scheduled_at
        timestamp processed_at
    }

    audit_logs {
        uuid id PK
        string entity_name
        uuid entity_id
        string action
        uuid actor_id
        uuid shg_id
        string client_ip
        string user_agent
        json before_state
        json after_state
        string prev_hash
        string row_hash UK
        timestamp created_at
    }
```

---

## 3. Transactional Guarantees & Resilience Patterns

### 3.1 Double-Entry Invariant Enforcement
Financial integrity is enforced at multiple defense layers:
1. **Per-Line Exclusive Constraint**: Database check constraint guarantees that exactly one side is non-zero:
   $$(debit > 0 \land credit = 0) \lor (debit = 0 \land credit > 0)$$
2. **Transaction Balance Verification**: In `app/domain/ledger/posting.py`, every posting validates:
   $$\sum \text{debits} - \sum \text{credits} = 0.00$$
   Any imbalance raises `LEDGER_UNBALANCED_ENTRY` and immediately rolls back the transaction.
3. **Append-Only Immutability**: Journal entries and lines cannot be updated or deleted. Corrections are executed via mirror reversal vouchers (`reverses_entry_id`). An entry can only be reversed once.

### 3.2 Transactional Outbox Pattern
To prevent dual-write bugs between PostgreSQL and asynchronous workers:
1. State mutations (disbursals, collections, repayments) write their domain records, ledger entries, and an `outbox_events` row in the **exact same database transaction**.
2. An ARQ worker polls `outbox_events` using `SELECT ... FOR UPDATE SKIP LOCKED`.
3. Consumers process events idempotently, updating denormalized read models (`dashboard_read_models`) and recalculating portfolio risk metrics (PAR 30/60/90).
4. Composite uniqueness on `(consumer_name, event_id)` prevents double-execution during worker failover or crash restarts.

### 3.3 Defense-in-Depth Row-Level Security (RLS)
Data tenancy is protected by two distinct layers:
1. **Application-Level Filtering**: Every query scopes explicitly by permitted `shg_id` retrieved from JWT session permissions.
2. **Postgres Row-Level Security**: Group-scoped tables enforce Postgres RLS using session settings (`SET LOCAL app.permitted_group_ids = '...'` and `SET LOCAL app.is_admin = 'true'`). Direct or accidental unfiltered SQL queries cannot cross group isolation boundaries.

### 3.4 Cryptographic SHA-256 Tamper-Evident Audit Chain
Every database write writes an audit event where:
$$\text{row\_hash} = \text{SHA256}(\text{prev\_hash} \mathbin{\Vert} \text{canonical\_json}(\text{entry}))$$
Using `python -m app.audit.verifier`, field supervisors or external auditors verify the entire blockchain-inspired audit log at > 20,000 rows/second, detecting unauthorized row tampering or deletion instantly.
