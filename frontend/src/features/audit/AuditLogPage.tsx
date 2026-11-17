import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../lib/api/client';
import type {
  AuditLogRowResponse,
  AuditVerificationResponse,
  AuditLogFilters,
} from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import {
  ShieldCheck,
  ShieldAlert,
  Download,
  Filter,
  CheckCircle2,
  X,
  User,
  Hash,
  Eye,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';

export const AuditLogPage: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogRowResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const pageSize = 15;

  // Filters
  const [actorId, setActorId] = useState('');
  const [entityType, setEntityType] = useState('');
  const [action, setAction] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');

  // Selected item for diff drawer
  const [selectedEntry, setSelectedEntry] = useState<AuditLogRowResponse | null>(null);

  // Verification state
  const [verification, setVerification] = useState<AuditVerificationResponse | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const filters: AuditLogFilters = {
        limit: pageSize,
        offset: page * pageSize,
      };
      if (actorId.trim()) filters.actor_id = actorId.trim();
      if (entityType.trim()) filters.entity_type = entityType.trim();
      if (action.trim()) filters.action = action.trim();
      if (fromDate) filters.from_date = fromDate;
      if (toDate) filters.to_date = toDate;

      const res = await apiClient.audit.list(filters);
      setLogs(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch audit logs';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, actorId, entityType, action, fromDate, toDate]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleVerifyChain = async () => {
    try {
      setVerifying(true);
      const res = await apiClient.audit.verify();
      setVerification(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Verification failed';
      setVerification({
        valid: false,
        count: 0,
        message: msg,
        error: msg,
      });
    } finally {
      setVerifying(false);
    }
  };

  const handleExportCsv = async () => {
    try {
      setExporting(true);
      const filters: AuditLogFilters = {};
      if (actorId.trim()) filters.actor_id = actorId.trim();
      if (entityType.trim()) filters.entity_type = entityType.trim();
      if (action.trim()) filters.action = action.trim();
      if (fromDate) filters.from_date = fromDate;
      if (toDate) filters.to_date = toDate;

      const blob = await apiClient.audit.exportCsv(filters);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Export failed';
      setError(msg);
    } finally {
      setExporting(false);
    }
  };

  const handleResetFilters = () => {
    setActorId('');
    setEntityType('');
    setAction('');
    setFromDate('');
    setToDate('');
    setPage(0);
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Page Header & Verification Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-[var(--primary)]" />
            <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
              Audit Trail & Chain Verification
            </h1>
          </div>
          <p className="text-sm text-[var(--muted-ink)] mt-0.5">
            Tamper-evident append-only ledger secured via SHA-256 cryptographic hash chaining
          </p>
        </div>

        {/* Verification Status & Action */}
        <div className="flex items-center flex-wrap gap-3">
          <div className="flex items-center gap-2 bg-[var(--surface)] border border-[var(--border)] px-3 py-1.5 rounded-lg text-xs shadow-sm">
            <span className="text-[var(--muted-ink)] font-medium">Chain Status:</span>
            {verification ? (
              verification.valid ? (
                <span className="flex items-center gap-1 text-[var(--primary)] font-semibold">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Chain Verified ({verification.count} rows)
                </span>
              ) : (
                <span className="flex items-center gap-1 text-danger font-bold">
                  <ShieldAlert className="w-3.5 h-3.5" /> Tampering Detected (Row {verification.broken_at_index})
                </span>
              )
            ) : (
              <span className="text-[var(--muted-ink)] italic">Unverified this session</span>
            )}
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleVerifyChain}
            disabled={verifying}
            className="flex items-center gap-1.5 text-xs font-semibold"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${verifying ? 'animate-spin' : ''}`} />
            {verifying ? 'Verifying...' : 'Verify Now'}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportCsv}
            disabled={exporting}
            className="flex items-center gap-1.5 text-xs"
          >
            <Download className="w-3.5 h-3.5" />
            {exporting ? 'Exporting...' : 'Export CSV'}
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-3.5 bg-surface-sunken border border-danger/30 rounded-lg flex items-start gap-2 text-xs text-danger">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Verification Details Banner (if verified) */}
      {verification && (
        <div
          className={`p-3.5 rounded-lg border text-xs flex items-center justify-between ${
            verification.valid
              ? 'bg-primary-tint border-primary/30 text-[var(--primary)]'
              : 'bg-surface-sunken border-danger/30 text-danger'
          }`}
        >
          <div className="flex items-center gap-2">
            {verification.valid ? (
              <ShieldCheck className="w-4 h-4 text-[var(--primary)] shrink-0" />
            ) : (
              <ShieldAlert className="w-4 h-4 text-danger shrink-0" />
            )}
            <span>{verification.message}</span>
          </div>
          {verification.valid && (
            <span className="font-mono text-[11px] text-[var(--muted-ink)]">
              Genesis: 0000000000000000...
            </span>
          )}
        </div>
      )}

      {/* Filter Controls Bar */}
      <div className="bg-[var(--surface)] p-4 rounded-xl border border-[var(--border)] shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--ink)]">
            <Filter className="w-3.5 h-3.5 text-[var(--primary)]" />
            <span>Filter Audit Trail</span>
          </div>
          <button
            type="button"
            onClick={handleResetFilters}
            className="text-xs text-[var(--muted-ink)] hover:text-[var(--ink)] underline cursor-pointer"
          >
            Reset Filters
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
          <div>
            <label className="block text-[11px] font-medium text-[var(--muted-ink)] mb-1">
              Entity Type
            </label>
            <select
              value={entityType}
              onChange={(e) => {
                setEntityType(e.target.value);
                setPage(0);
              }}
              className="w-full text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[var(--ink)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            >
              <option value="">All Entities</option>
              <option value="SHG">SHG (Group)</option>
              <option value="MEMBER">Member</option>
              <option value="LOAN">Loan</option>
              <option value="JOURNAL_ENTRY">Journal Entry</option>
              <option value="SAVINGS">Savings</option>
              <option value="MEETING">Meeting</option>
              <option value="USER">User</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-[var(--muted-ink)] mb-1">
              Action
            </label>
            <select
              value={action}
              onChange={(e) => {
                setAction(e.target.value);
                setPage(0);
              }}
              className="w-full text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[var(--ink)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            >
              <option value="">All Actions</option>
              <option value="CREATE">CREATE</option>
              <option value="UPDATE">UPDATE</option>
              <option value="APPROVE">APPROVE</option>
              <option value="REJECT">REJECT</option>
              <option value="DISBURSE">DISBURSE</option>
              <option value="REPAY">REPAY</option>
              <option value="REVERSE">REVERSE</option>
              <option value="COLLECT_SAVINGS">COLLECT_SAVINGS</option>
              <option value="WITHDRAW_SAVINGS">WITHDRAW_SAVINGS</option>
              <option value="BATCH_COLLECTION">BATCH_COLLECTION</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-[var(--muted-ink)] mb-1">
              Actor ID / UUID
            </label>
            <input
              type="text"
              placeholder="Filter by actor UUID"
              value={actorId}
              onChange={(e) => {
                setActorId(e.target.value);
                setPage(0);
              }}
              className="w-full text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[var(--ink)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)] font-mono"
            />
          </div>

          <div>
            <label className="block text-[11px] font-medium text-[var(--muted-ink)] mb-1">
              From Date
            </label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => {
                setFromDate(e.target.value);
                setPage(0);
              }}
              className="w-full text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[var(--ink)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
          </div>

          <div>
            <label className="block text-[11px] font-medium text-[var(--muted-ink)] mb-1">
              To Date
            </label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => {
                setToDate(e.target.value);
                setPage(0);
              }}
              className="w-full text-xs rounded border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[var(--ink)] focus:outline-none focus:ring-1 focus:ring-[var(--primary)]"
            />
          </div>
        </div>
      </div>

      {/* Audit Logs Table */}
      <div className="border border-[var(--border)] rounded-xl bg-[var(--surface)] shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-[var(--surface-muted)] border-b border-[var(--border)] text-[var(--muted-ink)] uppercase tracking-wider font-semibold">
              <tr>
                <th className="py-2.5 px-3">Timestamp (UTC)</th>
                <th className="py-2.5 px-3">Actor / Role</th>
                <th className="py-2.5 px-3">Action</th>
                <th className="py-2.5 px-3">Entity</th>
                <th className="py-2.5 px-3">Entity ID</th>
                <th className="py-2.5 px-3 font-mono">Row Hash</th>
                <th className="py-2.5 px-3 text-right">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)] text-[var(--ink)]">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-[var(--muted-ink)]">
                    Loading audit trail...
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-[var(--muted-ink)]">
                    No audit records match current filter criteria.
                  </td>
                </tr>
              ) : (
                logs.map((row) => (
                  <tr
                    key={row.id}
                    onClick={() => setSelectedEntry(row)}
                    className="hover:bg-[var(--surface-muted)] cursor-pointer transition-colors"
                  >
                    <td className="py-2.5 px-3 text-[var(--muted-ink)] font-mono whitespace-nowrap">
                      {new Date(row.occurred_at).toISOString().replace('T', ' ').slice(0, 19)}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1.5">
                        <User className="w-3 h-3 text-[var(--muted-ink)]" />
                        <span className="font-mono text-[11px]">
                          {row.actor_id ? row.actor_id.slice(0, 8) : 'SYSTEM'}
                        </span>
                        {row.actor_role && (
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-[var(--surface-muted)] border border-[var(--border)] text-[var(--muted-ink)] font-semibold">
                            {row.actor_role}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 font-semibold text-[var(--primary)]">
                      {row.action}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-[11px] bg-[var(--surface-muted)] px-1.5 py-0.5 rounded border border-[var(--border)]">
                        {row.entity_type}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-[var(--muted-ink)]">
                      {row.entity_id.slice(0, 8)}...
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[10px] text-[var(--muted-ink)]">
                      <span className="flex items-center gap-1">
                        <Hash className="w-3 h-3 text-[var(--primary)]" />
                        {row.row_hash.slice(0, 12)}...
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedEntry(row);
                        }}
                        className="p-1 rounded hover:bg-[var(--surface-muted)] text-[var(--primary)]"
                        title="View Before/After Diff"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        <div className="flex items-center justify-between p-3 border-t border-[var(--border)] bg-[var(--surface)] text-xs text-[var(--muted-ink)]">
          <div>
            Showing <span className="font-semibold text-[var(--ink)]">{logs.length > 0 ? page * pageSize + 1 : 0}</span> to{' '}
            <span className="font-semibold text-[var(--ink)]">
              {Math.min((page + 1) * pageSize, total)}
            </span>{' '}
            of <span className="font-semibold text-[var(--ink)]">{total}</span> records
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1.5"
              aria-label="Previous page"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <span className="font-mono text-[11px]">
              Page {page + 1} of {Math.max(1, totalPages)}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={page >= totalPages - 1}
              className="p-1.5"
              aria-label="Next page"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Before / After Diff Side Drawer */}
      {selectedEntry && (
        <>
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 transition-opacity"
            onClick={() => setSelectedEntry(null)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-label="Audit Record State Diff"
            className="fixed right-0 top-0 bottom-0 w-full max-w-2xl bg-[var(--surface)] border-l border-[var(--border)] shadow-2xl z-50 flex flex-col"
          >
            {/* Drawer Header */}
            <div className="p-4 border-b border-[var(--border)] flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-[var(--primary)]" />
                  <h3 className="font-serif text-lg font-bold text-[var(--ink)]">
                    Audit Entry Details & State Diff
                  </h3>
                </div>
                <p className="text-xs text-[var(--muted-ink)] mt-0.5 font-mono">
                  ID: {selectedEntry.id}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedEntry(null)}
                aria-label="Close diff drawer"
                className="p-1.5 rounded-lg text-[var(--muted-ink)] hover:text-[var(--ink)] hover:bg-[var(--surface-muted)] transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Body */}
            <div className="p-5 flex-1 overflow-y-auto space-y-4 text-xs">
              {/* Metadata Panel */}
              <div className="bg-[var(--surface-muted)] p-3.5 rounded-lg border border-[var(--border)] space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-[var(--muted-ink)] block">Action:</span>
                    <span className="font-bold text-[var(--primary)]">{selectedEntry.action}</span>
                  </div>
                  <div>
                    <span className="text-[var(--muted-ink)] block">Entity:</span>
                    <span className="font-mono">{selectedEntry.entity_type} ({selectedEntry.entity_id})</span>
                  </div>
                  <div>
                    <span className="text-[var(--muted-ink)] block">Actor:</span>
                    <span className="font-mono">
                      {selectedEntry.actor_id || 'SYSTEM'}{' '}
                      {selectedEntry.actor_role ? `(${selectedEntry.actor_role})` : ''}
                    </span>
                  </div>
                  <div>
                    <span className="text-[var(--muted-ink)] block">Occurred At:</span>
                    <span className="font-mono">
                      {new Date(selectedEntry.occurred_at).toLocaleString()}
                    </span>
                  </div>
                </div>

                <div className="pt-2 border-t border-[var(--border)] space-y-1 font-mono text-[11px] text-[var(--muted-ink)]">
                  <div className="truncate">
                    <span className="text-[var(--ink)]">Request ID:</span> {selectedEntry.request_id || 'n/a'}
                  </div>
                  <div className="truncate">
                    <span className="text-[var(--ink)]">Client IP:</span> {selectedEntry.ip || 'n/a'}
                  </div>
                  <div className="truncate">
                    <span className="text-[var(--ink)]">Prev Hash:</span> {selectedEntry.prev_hash || '0'.repeat(64)}
                  </div>
                  <div className="truncate">
                    <span className="text-[var(--ink)]">Row Hash:</span> {selectedEntry.row_hash}
                  </div>
                </div>
              </div>

              {/* State Diff Comparison */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-serif font-bold text-sm text-[var(--ink)]">
                    State Mutation (PII Masked)
                  </h4>
                  <span className="text-[11px] text-[var(--muted-ink)]">
                    {selectedEntry.before ? 'State Update' : 'New Creation'}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* Before */}
                  <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                    <div className="bg-surface-sunken px-3 py-1.5 border-b border-[var(--border)] font-semibold text-danger text-[11px] uppercase tracking-wider">
                      Before State
                    </div>
                    <pre className="p-3 bg-[var(--surface)] text-[11px] font-mono text-[var(--ink)] overflow-x-auto max-h-72">
                      {selectedEntry.before
                        ? JSON.stringify(selectedEntry.before, null, 2)
                        : '(null / initial state)'}
                    </pre>
                  </div>

                  {/* After */}
                  <div className="border border-[var(--border)] rounded-lg overflow-hidden">
                    <div className="bg-primary-tint px-3 py-1.5 border-b border-[var(--border)] font-semibold text-[var(--primary)] text-[11px] uppercase tracking-wider">
                      After State
                    </div>
                    <pre className="p-3 bg-[var(--surface)] text-[11px] font-mono text-[var(--ink)] overflow-x-auto max-h-72">
                      {selectedEntry.after
                        ? JSON.stringify(selectedEntry.after, null, 2)
                        : '(null / deleted)'}
                    </pre>
                  </div>
                </div>
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="p-3 border-t border-[var(--border)] bg-[var(--surface-muted)] flex justify-end">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setSelectedEntry(null)}
                className="text-xs"
              >
                Close Drawer
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
