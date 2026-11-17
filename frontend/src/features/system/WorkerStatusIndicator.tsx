import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '../../lib/api/client';
import type { WorkerStatusResponse } from '../../lib/api/types';
import { Activity, RefreshCw, AlertTriangle, CheckCircle, Clock } from 'lucide-react';

export const WorkerStatusIndicator: React.FC = () => {
  const [status, setStatus] = useState<WorkerStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await apiClient.system.getWorkerStatus();
      setStatus(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch status';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    // Poll every 15 seconds
    const timer = setInterval(fetchStatus, 15000);
    return () => clearInterval(timer);
  }, [fetchStatus]);

  if (!status && !loading && error) {
    return (
      <div
        className="flex items-center gap-1.5 px-2 py-1 text-xs rounded border border-[var(--border)] text-[var(--muted-ink)]"
        title={error}
        role="status"
        aria-label="Worker status unavailable"
      >
        <span className="w-2 h-2 rounded-full bg-[var(--danger)]" />
        <span className="font-mono text-[11px]">Worker: Err</span>
      </div>
    );
  }

  const isHealthy = status?.worker_status === 'HEALTHY';
  const isDegraded = status?.worker_status === 'DEGRADED';
  const lagSec = status?.lag_seconds ?? 0;
  const pendingCount = status?.pending_events_count ?? 0;
  const deadCount = status?.dead_letter_count ?? 0;

  return (
    <div className="relative inline-block text-left">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-label={`Outbox Worker Status: ${status?.worker_status || 'Checking'}, Lag: ${lagSec.toFixed(1)}s`}
        className="flex items-center gap-2 px-2.5 py-1 text-xs rounded-full border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-muted)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
      >
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${
            isHealthy
              ? 'bg-emerald-500 animate-pulse'
              : isDegraded
              ? 'bg-amber-500'
              : 'bg-slate-400'
          }`}
          aria-hidden="true"
        />
        <span className="font-medium text-[var(--ink)] text-[11px]">
          {isHealthy ? 'Worker Healthy' : isDegraded ? 'Worker Degraded' : 'Worker Idle'}
        </span>
        <span className="font-mono text-[11px] text-[var(--muted-ink)] hidden md:inline">
          Lag: {lagSec.toFixed(1)}s
        </span>
        {pendingCount > 0 && (
          <span className="bg-[var(--accent-subtle)] text-[var(--primary)] px-1.5 py-0.2 rounded-full text-[10px] font-mono font-semibold">
            {pendingCount}
          </span>
        )}
        {deadCount > 0 && (
          <span className="bg-red-100 text-red-700 px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold">
            !{deadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-label="Worker Diagnostics"
            className="absolute right-0 mt-2 w-80 rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 shadow-lg z-50 text-xs space-y-3"
          >
            <div className="flex items-center justify-between border-b border-[var(--border)] pb-2">
              <div className="flex items-center gap-1.5">
                <Activity className="w-4 h-4 text-[var(--primary)]" />
                <span className="font-semibold text-[var(--ink)]">Outbox & Worker Status</span>
              </div>
              <button
                type="button"
                onClick={fetchStatus}
                disabled={loading}
                aria-label="Refresh status"
                className="text-[var(--muted-ink)] hover:text-[var(--ink)] transition-colors p-1 rounded"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-[var(--muted-ink)]">Status:</span>
                <span className="font-semibold text-[var(--ink)] flex items-center gap-1">
                  {isHealthy ? (
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-600 inline" />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-600 inline" />
                  )}
                  {status?.worker_status || 'UNKNOWN'}
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-[var(--muted-ink)]">Queue Lag:</span>
                <span className="font-mono text-[var(--ink)] font-medium">
                  {lagSec.toFixed(2)}s
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-[var(--muted-ink)]">Pending Events:</span>
                <span className="font-mono text-[var(--ink)]">
                  {status?.pending_events_count ?? 0}
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-[var(--muted-ink)]">In Processing:</span>
                <span className="font-mono text-[var(--ink)]">
                  {status?.processing_events_count ?? 0}
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-[var(--muted-ink)]">Failed / Retrying:</span>
                <span className="font-mono text-[var(--ink)]">
                  {status?.failed_events_count ?? 0}
                </span>
              </div>

              <div className="flex justify-between items-center">
                <span className="text-[var(--muted-ink)]">Dead Letter Queue:</span>
                <span className={`font-mono ${deadCount > 0 ? 'text-red-600 font-bold' : 'text-[var(--ink)]'}`}>
                  {deadCount}
                </span>
              </div>

              <div className="flex justify-between items-center border-t border-[var(--border)] pt-2 text-[10px] text-[var(--muted-ink)]">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" /> Last event:
                </span>
                <span className="font-mono">
                  {status?.last_event_processed_at
                    ? new Date(status.last_event_processed_at).toLocaleTimeString()
                    : 'None yet'}
                </span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
