import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../lib/api/client';
import type { ReconciliationRunResponse, DiscrepancyItem } from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import {
  Scale,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  History,
  ShieldCheck,
  Building2,
  Clock,
} from 'lucide-react';

export const ReconciliationPage: React.FC = () => {
  const [latestRun, setLatestRun] = useState<ReconciliationRunResponse | null>(null);
  const [runsHistory, setRunsHistory] = useState<ReconciliationRunResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [latest, history] = await Promise.all([
        apiClient.reconciliation.getLatest(),
        apiClient.reconciliation.listRuns(10),
      ]);
      setLatestRun(latest);
      setRunsHistory(history);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load reconciliation data';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTriggerRun = async () => {
    try {
      setRunning(true);
      setError(null);
      setSuccessMessage(null);
      const res = await apiClient.reconciliation.run();
      setLatestRun(res);
      setRunsHistory((prev) => [res, ...prev.slice(0, 9)]);
      if (res.discrepancies_count === 0) {
        setSuccessMessage(
          `Reconciliation completed cleanly across ${res.groups_checked_count} groups in ${res.execution_time_ms}ms.`
        );
      } else {
        setError(
          `Reconciliation completed with ${res.discrepancies_count} discrepancies found across ${res.groups_checked_count} groups.`
        );
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Reconciliation run failed';
      setError(msg);
    } finally {
      setRunning(false);
    }
  };

  const discrepancies = (latestRun?.discrepancies || []) as unknown as DiscrepancyItem[];
  const isClean = latestRun && latestRun.discrepancies_count === 0;

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <Scale className="w-6 h-6 text-[var(--primary)]" />
            <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
              Ledger & Read-Model Reconciliation
            </h1>
          </div>
          <p className="text-sm text-[var(--muted-ink)] mt-0.5">
            Automated verification of double-entry journal lines against domain tables and outbox read-models
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={loadData}
            disabled={loading || running}
            className="flex items-center gap-1.5 text-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={handleTriggerRun}
            disabled={running}
            className="flex items-center gap-1.5 text-xs font-semibold"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
            {running ? 'Reconciling...' : 'Run Reconciliation Now'}
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="p-3.5 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 rounded-lg flex items-start gap-2 text-xs text-red-800 dark:text-red-300">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {successMessage && (
        <div className="p-3.5 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 rounded-lg flex items-start gap-2 text-xs text-emerald-800 dark:text-emerald-300">
          <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Latest Run Summary Card */}
      {latestRun ? (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] pb-3">
            <div className="flex items-center gap-3">
              <span className="text-xs uppercase tracking-wider font-semibold text-[var(--muted-ink)]">
                Latest Run Status:
              </span>
              <StatusChip
                status={latestRun.status}
                variant={latestRun.discrepancies_count === 0 ? 'active' : 'overdue'}
              >
                {latestRun.status === 'COMPLETED' ? 'CONSISTENT' : latestRun.status}
              </StatusChip>
            </div>

            <div className="flex items-center gap-4 text-xs text-[var(--muted-ink)]">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                {new Date(latestRun.run_at).toLocaleString()}
              </span>
              <span>·</span>
              <span className="font-mono">{latestRun.execution_time_ms} ms</span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1">
            <div className="bg-[var(--surface-muted)] p-3 rounded-lg border border-[var(--border)]">
              <div className="text-[11px] text-[var(--muted-ink)] uppercase tracking-wider">Groups Checked</div>
              <div className="text-xl font-bold font-serif text-[var(--ink)] mt-1">
                {latestRun.groups_checked_count}
              </div>
            </div>

            <div className="bg-[var(--surface-muted)] p-3 rounded-lg border border-[var(--border)]">
              <div className="text-[11px] text-[var(--muted-ink)] uppercase tracking-wider">Discrepancies</div>
              <div
                className={`text-xl font-bold font-serif mt-1 ${
                  latestRun.discrepancies_count === 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-red-600 dark:text-red-400'
                }`}
              >
                {latestRun.discrepancies_count}
              </div>
            </div>

            <div className="bg-[var(--surface-muted)] p-3 rounded-lg border border-[var(--border)]">
              <div className="text-[11px] text-[var(--muted-ink)] uppercase tracking-wider">Verification Vectors</div>
              <div className="text-xs font-medium text-[var(--ink)] mt-2">
                Cash · Savings · Loans
              </div>
            </div>

            <div className="bg-[var(--surface-muted)] p-3 rounded-lg border border-[var(--border)]">
              <div className="text-[11px] text-[var(--muted-ink)] uppercase tracking-wider">Run ID</div>
              <div className="text-xs font-mono text-[var(--muted-ink)] mt-2 truncate" title={latestRun.id}>
                {latestRun.id.slice(0, 13)}...
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-8 text-center text-[var(--muted-ink)]">
          <p className="text-sm">No reconciliation run has been executed yet.</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleTriggerRun}
            className="mt-3 text-xs"
            disabled={running}
          >
            Run Initial Reconciliation
          </Button>
        </div>
      )}

      {/* Discrepancy Details or Clean Empty State */}
      {latestRun && isClean && (
        <div className="bg-emerald-50/50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/40 rounded-xl p-8 text-center space-y-3">
          <div className="w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-900/50 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto">
            <ShieldCheck className="w-7 h-7" />
          </div>
          <h2 className="font-serif text-lg font-bold text-[var(--ink)]">
            All accounts, loan schedules, and read models reconcile cleanly.
          </h2>
          <p className="text-xs text-[var(--muted-ink)] max-w-lg mx-auto leading-relaxed">
            Every journal entry sums to zero, member sub-accounts match passbook balances,
            group cash equals physical ledger balances, and loan outstanding schedules agree with all disbursed portfolios.
          </p>
        </div>
      )}

      {latestRun && !isClean && discrepancies.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600" />
            <h2 className="font-serif text-base font-bold text-[var(--ink)]">
              Detected Discrepancies ({discrepancies.length})
            </h2>
          </div>

          <div className="w-full overflow-x-auto border border-[var(--border)] rounded-xl bg-[var(--surface)] shadow-sm">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-[var(--surface-muted)] border-b border-[var(--border)] text-[var(--muted-ink)] uppercase tracking-wider font-semibold">
                <tr>
                  <th className="py-2.5 px-3">Entity Type</th>
                  <th className="py-2.5 px-3">Group</th>
                  <th className="py-2.5 px-3">Entity Details</th>
                  <th className="py-2.5 px-3 text-right">Ledger Value</th>
                  <th className="py-2.5 px-3 text-right">Domain/Read-Model</th>
                  <th className="py-2.5 px-3 text-right">Difference</th>
                  <th className="py-2.5 px-3">Explanation</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)] text-[var(--ink)]">
                {discrepancies.map((d, idx) => (
                  <tr key={idx} className="hover:bg-[var(--surface-muted)] transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-[var(--primary)]">
                      {d.entity_type}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1">
                        <Building2 className="w-3.5 h-3.5 text-[var(--muted-ink)]" />
                        <span>{d.shg_name || d.shg_id.slice(0, 8)}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 font-mono">
                      {d.member_name ? (
                        <div>
                          <span className="font-sans font-medium">{d.member_name}</span>
                          <span className="block text-[10px] text-[var(--muted-ink)]">
                            {d.entity_id.slice(0, 8)}
                          </span>
                        </div>
                      ) : (
                        d.entity_id.slice(0, 8)
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-medium">
                      ₹{d.ledger_value}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-medium">
                      ₹{d.domain_value}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-red-600 dark:text-red-400">
                      ₹{d.difference}
                    </td>
                    <td className="py-2.5 px-3 text-[var(--muted-ink)] max-w-xs truncate" title={d.explanation}>
                      {d.explanation}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Historical Runs */}
      {runsHistory.length > 0 && (
        <div className="space-y-3 pt-4 border-t border-[var(--border)]">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-[var(--muted-ink)]" />
            <h2 className="font-serif text-base font-bold text-[var(--ink)]">
              Reconciliation Run History
            </h2>
          </div>

          <div className="w-full overflow-x-auto border border-[var(--border)] rounded-xl bg-[var(--surface)]">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-[var(--surface-muted)] border-b border-[var(--border)] text-[var(--muted-ink)] uppercase tracking-wider font-semibold">
                <tr>
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-center">Groups</th>
                  <th className="py-2.5 px-3 text-center">Discrepancies</th>
                  <th className="py-2.5 px-3 text-right">Execution Time</th>
                  <th className="py-2.5 px-3 font-mono">Run ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)] text-[var(--ink)]">
                {runsHistory.map((run) => (
                  <tr key={run.id} className="hover:bg-[var(--surface-muted)] transition-colors">
                    <td className="py-2.5 px-3 text-[var(--muted-ink)]">
                      {new Date(run.run_at).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3">
                      <StatusChip
                        status={run.status}
                        variant={run.discrepancies_count === 0 ? 'active' : 'overdue'}
                      >
                        {run.discrepancies_count === 0 ? 'CONSISTENT' : 'DISCREPANCIES'}
                      </StatusChip>
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono">
                      {run.groups_checked_count}
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono font-medium">
                      {run.discrepancies_count}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-[var(--muted-ink)]">
                      {run.execution_time_ms} ms
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[10px] text-[var(--muted-ink)]">
                      {run.id.slice(0, 8)}...
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
