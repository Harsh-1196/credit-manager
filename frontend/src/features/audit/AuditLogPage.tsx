import React from 'react';
import { ShieldCheck, Terminal, Hash, Lock } from 'lucide-react';

export const AuditLogPage: React.FC = () => {
  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
          Audit Trail & Cryptographic Verification
        </h1>
        <p className="text-sm text-[var(--muted-ink)] mt-0.5">
          Tamper-evident append-only journal secured via SHA-256 hash chaining
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)]">
          <div className="flex items-center gap-2 text-[var(--primary)] font-medium text-xs mb-1">
            <Lock className="w-4 h-4" />
            <span>Append-Only Ledger</span>
          </div>
          <p className="text-xs text-[var(--muted-ink)] leading-relaxed">
            Every mutating request writes an immutable record with before/after state and masked PII.
          </p>
        </div>

        <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)]">
          <div className="flex items-center gap-2 text-[var(--primary)] font-medium text-xs mb-1">
            <Hash className="w-4 h-4" />
            <span>SHA-256 Chain</span>
          </div>
          <p className="text-xs text-[var(--muted-ink)] leading-relaxed">
            Each row hash is derived from the canonical JSON representation and the preceding row's hash.
          </p>
        </div>

        <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)]">
          <div className="flex items-center gap-2 text-[var(--primary)] font-medium text-xs mb-1">
            <ShieldCheck className="w-4 h-4" />
            <span>Tamper Detection</span>
          </div>
          <p className="text-xs text-[var(--muted-ink)] leading-relaxed">
            Any modification, insertion, or deletion breaks the cryptographic chain and points directly to the compromised entry.
          </p>
        </div>
      </div>

      <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)] space-y-4">
        <h2 className="font-serif text-base font-bold text-[var(--ink)]">
          Independent Chain Verification CLI
        </h2>
        <p className="text-xs text-[var(--muted-ink)]">
          Auditors and system administrators can independently verify the cryptographic integrity
          of the entire database audit chain using the management CLI:
        </p>

        <div className="bg-[var(--surface-muted)] p-3 rounded font-mono text-xs text-[var(--ink)] border border-[var(--border)] flex items-center justify-between">
          <span>python -m app.audit.verifier</span>
          <Terminal className="w-4 h-4 text-[var(--muted-ink)]" />
        </div>

        <p className="text-[11px] text-[var(--muted-ink)] font-mono">
          Specification: SPEC.md Section 10 · Genesis hash: 64 zeros · SHA-256(prev_hash || canonical_json(row))
        </p>
      </div>
    </div>
  );
};
