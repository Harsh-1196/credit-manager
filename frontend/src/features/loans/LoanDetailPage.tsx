import React, { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { parseMoney } from '../../lib/money';
import type {
  LoanDisbursePreviewResponse,
  LoanRepayPreviewResponse,
} from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { MoneyText } from '../../components/ui/MoneyText';
import { Skeleton } from '../../components/ui/Skeleton';
import { StatusChip } from '../../components/ui/StatusChip';
import {
  ArrowLeft,
  XCircle,
  AlertCircle,
  ShieldAlert,
  Send,
  CheckCircle2,
  Banknote,
  Receipt,
  FileX2,
} from 'lucide-react';

export const LoanDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { user } = useAuth();

  // Modals state
  const [isRejectOpen, setIsRejectOpen] = useState(false);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectionError, setRejectionError] = useState<string | null>(null);

  const [isDisburseOpen, setIsDisburseOpen] = useState(false);
  const [firstDueDate, setFirstDueDate] = useState('');
  const [disburseError, setDisburseError] = useState<string | null>(null);

  const [isRepayOpen, setIsRepayOpen] = useState(false);
  const [repayAmount, setRepayAmount] = useState('');
  const [repayDate, setRepayDate] = useState(new Date().toISOString().split('T')[0]);
  const [repayError, setRepayError] = useState<string | null>(null);

  const [isWriteOffOpen, setIsWriteOffOpen] = useState(false);
  const [writeOffReason, setWriteOffReason] = useState('');
  const [writeOffError, setWriteOffError] = useState<string | null>(null);

  const [actionNotice, setActionNotice] = useState<string | null>(null);

  // Queries
  const {
    data: loan,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['loan', id],
    queryFn: () => (id ? api.loans.get(id) : Promise.reject('No ID')),
    enabled: !!id,
  });

  const { data: history } = useQuery({
    queryKey: ['loan-history', id],
    queryFn: () => (id ? api.loans.history(id) : Promise.reject('No ID')),
    enabled: !!id,
  });

  // Disburse Preview Query (only when disburse modal is open)
  const { data: disbursePreview, isLoading: isDisbursePreviewLoading } =
    useQuery<LoanDisbursePreviewResponse>({
      queryKey: ['loan-disburse-preview', id],
      queryFn: () => (id ? api.loans.getDisbursePreview(id) : Promise.reject('No ID')),
      enabled: !!id && isDisburseOpen,
    });

  // Repayment Live Preview Query using parseMoney (strictly no parseFloat)
  let cleanRepayDecimal: string | null = null;
  try {
    if (repayAmount.trim()) {
      const parsed = parseMoney(repayAmount);
      if (parsed.isPositive() && !parsed.isZero()) {
        cleanRepayDecimal = parsed.toFixed(2);
      }
    }
  } catch {
    cleanRepayDecimal = null;
  }

  const { data: repayPreview, isLoading: isRepayPreviewLoading } =
    useQuery<LoanRepayPreviewResponse>({
      queryKey: ['loan-repay-preview', id, cleanRepayDecimal, repayDate],
      queryFn: () =>
        id && cleanRepayDecimal
          ? api.loans.previewRepayment(id, {
              amount: cleanRepayDecimal,
              payment_date: repayDate || undefined,
            })
          : Promise.reject('Invalid amount'),
      enabled: !!id && isRepayOpen && !!cleanRepayDecimal,
      retry: false,
    });

  // Mutations
  const submitMutation = useMutation({
    mutationFn: async () => {
      if (!id) return;
      return api.loans.submit(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loan', id] });
      queryClient.invalidateQueries({ queryKey: ['loan-history', id] });
      setActionNotice('Application submitted successfully.');
    },
    onError: (err: unknown) => {
      setActionNotice(err instanceof ApiException ? err.message : 'Failed to submit loan.');
    },
  });

  const approveMutation = useMutation({
    mutationFn: async () => {
      if (!id || !loan) return;
      return api.loans.approve(id, { version: loan.version });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loan', id] });
      queryClient.invalidateQueries({ queryKey: ['loan-history', id] });
      setActionNotice('Loan approved successfully.');
    },
    onError: (err: unknown) => {
      setActionNotice(err instanceof ApiException ? err.message : 'Failed to approve loan.');
    },
  });

  const rejectMutation = useMutation({
    mutationFn: async (reason: string) => {
      if (!id || !loan) return;
      return api.loans.reject(id, { version: loan.version, reason });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loan', id] });
      queryClient.invalidateQueries({ queryKey: ['loan-history', id] });
      setIsRejectOpen(false);
      setRejectionReason('');
      setActionNotice('Loan application rejected.');
    },
    onError: (err: unknown) => {
      setRejectionError(err instanceof ApiException ? err.message : 'Failed to reject loan.');
    },
  });

  const disburseMutation = useMutation({
    mutationFn: async () => {
      if (!id || !loan) return;
      const idempotencyKey = `disburse-${loan.id}-${loan.version}-${Date.now()}`;
      return api.loans.disburse(
        id,
        {
          version: loan.version,
          first_due_date: firstDueDate || undefined,
        },
        idempotencyKey
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loan', id] });
      queryClient.invalidateQueries({ queryKey: ['loan-history', id] });
      setIsDisburseOpen(false);
      setActionNotice('Loan disbursed and repayment schedule activated.');
    },
    onError: (err: unknown) => {
      setDisburseError(err instanceof ApiException ? err.message : 'Failed to disburse loan.');
    },
  });

  const repayMutation = useMutation({
    mutationFn: async () => {
      if (!id || !loan) return;
      if (!cleanRepayDecimal) throw new Error('Invalid repayment amount');
      const idempotencyKey = `repay-${loan.id}-${Date.now()}`;
      return api.loans.repay(
        id,
        {
          amount: cleanRepayDecimal,
          payment_date: repayDate || undefined,
          version: loan.version,
        },
        idempotencyKey
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loan', id] });
      queryClient.invalidateQueries({ queryKey: ['loan-history', id] });
      setIsRepayOpen(false);
      setRepayAmount('');
      setActionNotice('Repayment recorded and ledger entries posted successfully.');
    },
    onError: (err: unknown) => {
      setRepayError(err instanceof ApiException ? err.message : 'Failed to record repayment.');
    },
  });

  const writeOffMutation = useMutation({
    mutationFn: async () => {
      if (!id || !loan) return;
      return api.loans.writeOff(id, {
        version: loan.version,
        reason: writeOffReason.trim(),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loan', id] });
      queryClient.invalidateQueries({ queryKey: ['loan-history', id] });
      setIsWriteOffOpen(false);
      setWriteOffReason('');
      setActionNotice('Loan has been written off and bad debt ledger entry posted.');
    },
    onError: (err: unknown) => {
      setWriteOffError(err instanceof ApiException ? err.message : 'Failed to write off loan.');
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6 max-w-7xl mx-auto p-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (isError || !loan) {
    return (
      <div className="p-12 text-center max-w-xl mx-auto">
        <AlertCircle className="w-8 h-8 text-danger mx-auto mb-2" />
        <h2 className="font-serif text-lg font-bold text-[var(--ink)]">Loan Not Found</h2>
        <p className="text-xs text-[var(--muted-ink)] mt-1 mb-4">
          The requested loan could not be retrieved or is outside your permitted groups.
        </p>
        <Link to="/loans/approvals">
          <Button variant="secondary" size="sm">
            Back to Approvals Queue
          </Button>
        </Link>
      </div>
    );
  }

  const canApprove = loan.can_approve ?? true;
  const isLeaderOrAdmin = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';
  const isAdmin = user?.role === 'ADMIN';
  const summary = loan.summary;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-[var(--border)] pb-4 gap-4">
        <div className="flex items-center gap-3">
          <Link
            to="/loans/approvals"
            aria-label="Back to approvals queue"
            className="p-1.5 rounded hover:bg-[var(--surface-muted)] text-[var(--muted-ink)] hover:text-[var(--ink)]"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-serif text-xl font-bold tracking-tight text-[var(--ink)] font-mono">
                {loan.loan_number}
              </h1>
              <StatusChip status={loan.status} />
              <span className="text-[10px] font-mono text-[var(--muted-ink)] border border-[var(--border)] px-1.5 py-0.5 rounded">
                v{loan.version}
              </span>
            </div>
            <p className="text-xs text-[var(--muted-ink)] mt-0.5">
              Borrower: <strong className="text-[var(--ink)]">{loan.member_name || 'Member'}</strong> | Purpose: {loan.purpose}
            </p>
          </div>
        </div>

        {/* Top Quick Actions */}
        <div className="flex items-center gap-2">
          {loan.status === 'DRAFT' && isLeaderOrAdmin && (
            <Button
              variant="primary"
              size="sm"
              disabled={submitMutation.isPending}
              onClick={() => submitMutation.mutate()}
            >
              <Send className="w-3.5 h-3.5 mr-1.5" />
              {submitMutation.isPending ? 'Submitting...' : 'Submit Application'}
            </Button>
          )}

          {loan.status === 'SUBMITTED' && isLeaderOrAdmin && (
            <>
              <Button
                variant="primary"
                size="sm"
                disabled={!canApprove || approveMutation.isPending}
                onClick={() => approveMutation.mutate()}
                title={canApprove ? 'Approve Loan' : loan.maker_checker_note || 'Maker-checker restriction'}
              >
                <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                {approveMutation.isPending ? 'Approving...' : 'Approve'}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setIsRejectOpen(true);
                  setRejectionReason('');
                  setRejectionError(null);
                }}
              >
                Reject
              </Button>
            </>
          )}

          {loan.status === 'APPROVED' && isLeaderOrAdmin && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setIsDisburseOpen(true);
                setDisburseError(null);
              }}
            >
              <Banknote className="w-3.5 h-3.5 mr-1.5" />
              Disburse Loan
            </Button>
          )}

          {(loan.status === 'ACTIVE' || loan.status === 'OVERDUE') && isLeaderOrAdmin && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setIsRepayOpen(true);
                setRepayAmount('');
                setRepayError(null);
              }}
            >
              <Receipt className="w-3.5 h-3.5 mr-1.5" />
              Record Repayment
            </Button>
          )}

          {loan.status === 'OVERDUE' && isAdmin && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => {
                setIsWriteOffOpen(true);
                setWriteOffReason('');
                setWriteOffError(null);
              }}
            >
              <FileX2 className="w-3.5 h-3.5 mr-1.5" />
              Write Off Loan
            </Button>
          )}
        </div>
      </div>

      {/* Notifications and Alerts */}
      {actionNotice && (
        <div className="p-3.5 rounded border border-[var(--primary)]/30 bg-surface-sunken flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-[var(--primary)]" />
            <span className="text-[var(--ink)] font-medium">{actionNotice}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setActionNotice(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {loan.status === 'SUBMITTED' && !canApprove && (
        <div className="p-3.5 rounded border border-warning/30 bg-surface-sunken flex items-start gap-2.5">
          <ShieldAlert className="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <div className="text-xs">
            <span className="font-semibold text-warning">[MAKER-CHECKER RESTRICTION] </span>
            <span className="text-[var(--ink)]">{loan.maker_checker_note}</span>
          </div>
        </div>
      )}

      {loan.status === 'REJECTED' && loan.rejection_reason && (
        <div className="p-3.5 rounded border border-danger/30 bg-surface-sunken flex items-start gap-3">
          <XCircle className="w-4 h-4 text-danger shrink-0 mt-0.5" />
          <div className="text-xs">
            <h4 className="font-semibold text-danger uppercase tracking-wider text-[10px]">
              Application Rejected
            </h4>
            <p className="text-[var(--ink)] mt-0.5">{loan.rejection_reason}</p>
          </div>
        </div>
      )}

      {loan.status === 'WRITTEN_OFF' && (
        <div className="p-3.5 rounded border border-danger/30 bg-surface-sunken flex items-start gap-3">
          <FileX2 className="w-4 h-4 text-danger shrink-0 mt-0.5" />
          <div className="text-xs">
            <h4 className="font-semibold text-danger uppercase tracking-wider text-[10px]">
              Loan Written Off
            </h4>
            <p className="text-[var(--ink)] mt-0.5">
              Reason: {loan.write_off_reason || 'Bad debt write-off by Administrator.'}
            </p>
          </div>
        </div>
      )}

      {/* SCREEN 8 3-COLUMN EDITORIAL LAYOUT */}
      <div className="grid grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: State Timeline with actor and time */}
        <div className="col-span-12 lg:col-span-3 bg-[var(--surface)] border border-[var(--border)] rounded p-4 space-y-3 shadow-sm">
          <h3 className="font-serif text-sm font-semibold text-[var(--ink)] uppercase tracking-wider text-[11px] border-b border-[var(--border)] pb-2">
            Status Timeline
          </h3>

          {history && history.length > 0 ? (
            <div className="relative border-l-2 border-[var(--border)] pl-3.5 ml-2 space-y-4 pt-1">
              {history.map((h) => (
                <div key={h.id} className="relative text-xs space-y-1">
                  <div className="absolute -left-[19px] top-1 w-2.5 h-2.5 rounded-full bg-[var(--primary)] border-2 border-[var(--surface)]" />
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono font-semibold text-[var(--ink)]">
                      {h.from_status} → {h.to_status}
                    </span>
                  </div>
                  <div className="text-[10px] text-[var(--muted-ink)] font-mono">
                    {new Date(h.created_at).toLocaleString('en-IN', {
                      dateStyle: 'short',
                      timeStyle: 'short',
                    })}
                  </div>
                  {h.reason && (
                    <p className="text-[11px] text-[var(--muted-ink)] italic bg-surface-sunken p-1.5 rounded">
                      "{h.reason}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-[var(--muted-ink)] py-2">
              No status transitions recorded yet.
            </p>
          )}

          <div className="pt-3 border-t border-[var(--border)] text-[11px] text-[var(--muted-ink)] space-y-1">
            <div>
              <strong>Applied:</strong> {loan.applied_at ? new Date(loan.applied_at).toLocaleDateString('en-IN') : 'Pending'}
            </div>
            <div>
              <strong>Approved:</strong> {loan.approved_at ? new Date(loan.approved_at).toLocaleDateString('en-IN') : 'Pending'}
            </div>
            <div>
              <strong>Disbursed:</strong> {loan.disbursed_at ? new Date(loan.disbursed_at).toLocaleDateString('en-IN') : 'Pending'}
            </div>
            {loan.closed_at && (
              <div>
                <strong>Closed:</strong> {new Date(loan.closed_at).toLocaleDateString('en-IN')}
              </div>
            )}
          </div>
        </div>

        {/* CENTER COLUMN: Repayment Schedule Table with status chips & "Overdue N days" cue */}
        <div className="col-span-12 lg:col-span-6 bg-[var(--surface)] border border-[var(--border)] rounded p-4 space-y-3 shadow-sm">
          <div className="flex items-center justify-between border-b border-[var(--border)] pb-2">
            <h3 className="font-serif text-sm font-semibold text-[var(--ink)] uppercase tracking-wider text-[11px]">
              Repayment Schedule
            </h3>
            <span className="text-[11px] font-mono text-[var(--muted-ink)]">
              {loan.schedule?.length || 0} Installments ({loan.interest_type})
            </span>
          </div>

          <div className="overflow-x-auto border border-[var(--border)] rounded">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-[var(--surface-muted)] text-[var(--muted-ink)] border-b border-[var(--border)] font-semibold uppercase text-[10px] tracking-wider">
                  <th className="py-2 px-2.5">#</th>
                  <th className="py-2 px-2.5">Due Date</th>
                  <th className="py-2 px-2.5 text-right">Principal</th>
                  <th className="py-2 px-2.5 text-right">Interest</th>
                  <th className="py-2 px-2.5 text-right">Penalty</th>
                  <th className="py-2 px-2.5 text-right">Total</th>
                  <th className="py-2 px-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)] font-mono">
                {loan.schedule && loan.schedule.length > 0 ? (
                  loan.schedule.map((inst) => (
                    <tr
                      key={inst.installment_no}
                      className="hover:bg-[var(--surface-muted)]/50 transition-colors"
                    >
                      <td className="py-2 px-2.5 text-[var(--ink)]">{inst.installment_no}</td>
                      <td className="py-2 px-2.5 text-[var(--ink)]">
                        <div>{inst.due_date}</div>
                        {inst.days_overdue > 0 && (
                          <span className="inline-block text-[10px] text-danger font-sans font-medium">
                            Overdue {inst.days_overdue} days
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2.5 text-right tabular-nums text-[var(--ink)]">
                        <MoneyText amount={inst.principal_due} />
                      </td>
                      <td className="py-2 px-2.5 text-right tabular-nums text-[var(--ink)]">
                        <MoneyText amount={inst.interest_due} />
                      </td>
                      <td className="py-2 px-2.5 text-right tabular-nums text-[var(--ink)]">
                        <MoneyText amount={inst.penalty_due || '0.00'} />
                      </td>
                      <td className="py-2 px-2.5 text-right tabular-nums font-semibold text-[var(--ink)]">
                        <MoneyText amount={inst.total_due} />
                      </td>
                      <td className="py-2 px-2.5 font-sans">
                        <StatusChip status={inst.status} />
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-xs text-[var(--muted-ink)]">
                      Schedule generated upon loan disbursal.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* RIGHT COLUMN: Summary Panel & Actions */}
        <div className="col-span-12 lg:col-span-3 space-y-4">
          {/* Summary Panel */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded p-4 space-y-3 shadow-sm">
            <h3 className="font-serif text-sm font-semibold text-[var(--ink)] uppercase tracking-wider text-[11px] border-b border-[var(--border)] pb-2">
              Loan Balances
            </h3>

            <div className="space-y-2.5 text-xs">
              <div>
                <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                  Outstanding Principal
                </span>
                <MoneyText
                  amount={summary?.outstanding_principal || loan.principal}
                  className="text-lg font-bold font-mono text-[var(--ink)]"
                />
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div>
                  <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                    Interest Due
                  </span>
                  <MoneyText
                    amount={summary?.outstanding_interest || '0.00'}
                    className="text-xs font-mono text-[var(--ink)]"
                  />
                </div>
                <div>
                  <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                    Penalty Due
                  </span>
                  <MoneyText
                    amount={summary?.outstanding_penalty || '0.00'}
                    className="text-xs font-mono text-danger font-medium"
                  />
                </div>
              </div>

              <div className="pt-2 border-t border-[var(--border)]">
                <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                  Total Payoff Balance
                </span>
                <MoneyText
                  amount={summary?.total_outstanding_balance || loan.principal}
                  className="text-base font-semibold font-mono text-[var(--primary)]"
                />
              </div>

              {summary?.next_due_date && (
                <div className="pt-2 border-t border-[var(--border)] bg-surface-sunken p-2 rounded">
                  <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                    Next Due
                  </span>
                  <div className="flex items-center justify-between mt-0.5">
                    <span className="font-mono text-xs text-[var(--ink)]">
                      {summary.next_due_date}
                    </span>
                    <MoneyText
                      amount={summary.next_due_amount}
                      className="font-mono font-semibold text-xs text-[var(--ink)]"
                    />
                  </div>
                  {summary.days_overdue > 0 && (
                    <div className="text-[10px] text-danger font-semibold mt-1">
                      Arrears: Overdue {summary.days_overdue} days
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Action Center Card */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded p-4 space-y-3 shadow-sm">
            <h3 className="font-serif text-sm font-semibold text-[var(--ink)] uppercase tracking-wider text-[11px] border-b border-[var(--border)] pb-2">
              Available Actions
            </h3>

            <div className="space-y-2">
              {loan.status === 'APPROVED' && isLeaderOrAdmin && (
                <Button
                  variant="primary"
                  className="w-full justify-center"
                  onClick={() => {
                    setIsDisburseOpen(true);
                    setDisburseError(null);
                  }}
                >
                  <Banknote className="w-4 h-4 mr-1.5" />
                  Disburse Loan
                </Button>
              )}

              {(loan.status === 'ACTIVE' || loan.status === 'OVERDUE') && isLeaderOrAdmin && (
                <Button
                  variant="primary"
                  className="w-full justify-center"
                  onClick={() => {
                    setIsRepayOpen(true);
                    setRepayAmount('');
                    setRepayError(null);
                  }}
                >
                  <Receipt className="w-4 h-4 mr-1.5" />
                  Record Repayment
                </Button>
              )}

              {loan.status === 'OVERDUE' && isAdmin && (
                <Button
                  variant="danger"
                  className="w-full justify-center"
                  onClick={() => {
                    setIsWriteOffOpen(true);
                    setWriteOffReason('');
                    setWriteOffError(null);
                  }}
                >
                  <FileX2 className="w-4 h-4 mr-1.5" />
                  Write Off Loan
                </Button>
              )}

              {loan.status === 'CLOSED' && (
                <div className="p-3 bg-surface-sunken rounded text-center text-xs text-[var(--muted-ink)]">
                  Loan is settled in full and closed.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* DISBURSE DIALOG (Screen 8 requirement) */}
      {isDisburseOpen && (
        <Dialog
          isOpen={true}
          onClose={() => setIsDisburseOpen(false)}
          title="Disburse Loan & Confirm Journal Lines"
        >
          <div className="space-y-4 text-xs">
            {isDisbursePreviewLoading ? (
              <div className="space-y-3 py-4">
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-20 w-full" />
              </div>
            ) : disbursePreview ? (
              <>
                {/* Restated Loan Figures */}
                <div className="p-3 bg-surface-sunken rounded border border-[var(--border)] space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-[var(--muted-ink)]">Borrower:</span>
                    <strong className="text-[var(--ink)]">{disbursePreview.member_name}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--muted-ink)]">Loan Principal:</span>
                    <MoneyText amount={disbursePreview.principal} className="font-semibold text-[var(--ink)]" />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--muted-ink)]">Processing Fee (Deducted):</span>
                    <MoneyText amount={disbursePreview.processing_fee} className="text-[var(--muted-ink)]" />
                  </div>
                  <div className="flex justify-between pt-1 border-t border-[var(--border)]">
                    <span className="font-semibold text-[var(--ink)]">Net Disbursed to Member:</span>
                    <MoneyText amount={disbursePreview.net_disbursed} className="font-bold text-[var(--primary)] text-sm" />
                  </div>
                </div>

                {/* Group Cash Check Indicator */}
                <div className={`p-2.5 rounded border text-xs flex items-center justify-between ${
                  disbursePreview.has_sufficient_cash
                    ? 'border-[var(--primary)]/30 bg-[var(--surface-muted)] text-[var(--ink)]'
                    : 'border-danger/30 bg-danger/10 text-danger'
                }`}>
                  <span>Group Cash in Hand Balance:</span>
                  <div className="flex items-center gap-1.5">
                    <MoneyText amount={disbursePreview.group_cash_balance} className="font-mono font-bold" />
                    <span className="text-[10px] font-semibold">
                      {disbursePreview.has_sufficient_cash ? '[SUFFICIENT]' : '[INSUFFICIENT FUNDS]'}
                    </span>
                  </div>
                </div>

                {/* Journal Lines That Will Be Posted */}
                <div className="space-y-1.5">
                  <h4 className="font-semibold uppercase text-[10px] tracking-wider text-[var(--muted-ink)]">
                    Double-Entry Journal Lines to Post
                  </h4>
                  <div className="border border-[var(--border)] rounded overflow-hidden">
                    <table className="w-full text-[11px] border-collapse font-mono">
                      <thead className="bg-[var(--surface-muted)] text-[var(--muted-ink)] border-b border-[var(--border)]">
                        <tr>
                          <th className="py-1 px-2 text-left font-sans">Account</th>
                          <th className="py-1 px-2 text-right">Debit</th>
                          <th className="py-1 px-2 text-right">Credit</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border)]">
                        {disbursePreview.journal_lines.map((line, idx) => (
                          <tr key={idx}>
                            <td className="py-1 px-2 text-[var(--ink)] font-sans">
                              {line.account_code} - {line.account_name}
                            </td>
                            <td className="py-1 px-2 text-right text-[var(--ink)]">
                              {line.debit !== '0.00' ? <MoneyText amount={line.debit} /> : '-'}
                            </td>
                            <td className="py-1 px-2 text-right text-[var(--ink)]">
                              {line.credit !== '0.00' ? <MoneyText amount={line.credit} /> : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* First Due Date Override */}
                <div>
                  <label htmlFor="first-due-date" className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                    First Due Date (Optional)
                  </label>
                  <Input
                    id="first-due-date"
                    aria-label="First Due Date"
                    type="date"
                    value={firstDueDate}
                    onChange={(e) => setFirstDueDate(e.target.value)}
                  />
                </div>

                {disburseError && (
                  <p className="text-xs text-danger">{disburseError}</p>
                )}

                <div className="flex justify-end gap-3 pt-3 border-t border-[var(--border)]">
                  <Button variant="secondary" onClick={() => setIsDisburseOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    disabled={!disbursePreview.has_sufficient_cash || disburseMutation.isPending}
                    onClick={() => disburseMutation.mutate()}
                  >
                    {disburseMutation.isPending ? 'Posting Disbursal...' : 'Confirm & Disburse'}
                  </Button>
                </div>
              </>
            ) : (
              <p className="text-xs text-danger">Failed to load disbursal preview.</p>
            )}
          </div>
        </Dialog>
      )}

      {/* REPAYMENT DIALOG (Screen 8 requirement with live allocation breakdown) */}
      {isRepayOpen && (
        <Dialog
          isOpen={true}
          onClose={() => setIsRepayOpen(false)}
          title="Record Loan Repayment"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="repay-amount" className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                  Repayment Amount (₹) *
                </label>
                <Input
                  id="repay-amount"
                  aria-label="Repayment Amount in Rupees"
                  type="number"
                  step="0.01"
                  value={repayAmount}
                  onChange={(e) => {
                    setRepayAmount(e.target.value);
                    if (repayError) setRepayError(null);
                  }}
                  placeholder="e.g. 2500.00"
                />
              </div>
              <div>
                <label htmlFor="repay-date" className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                  Payment Date
                </label>
                <Input
                  id="repay-date"
                  aria-label="Payment Date"
                  type="date"
                  value={repayDate}
                  onChange={(e) => setRepayDate(e.target.value)}
                />
              </div>
            </div>

            {/* Live Allocation Breakdown Preview */}
            {isRepayPreviewLoading && (
              <div className="p-3 bg-surface-sunken rounded border border-[var(--border)] space-y-1">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-4 w-56" />
              </div>
            )}

            {repayPreview && (
              <div className="p-3 bg-surface-sunken rounded border border-[var(--border)] space-y-2">
                <h4 className="font-semibold uppercase text-[10px] tracking-wider text-[var(--primary)]">
                  Live Repayment Allocation (SPEC 6.4)
                </h4>
                <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                  <div>
                    <span className="text-[var(--muted-ink)] font-sans">Penalty Paid:</span>{' '}
                    <MoneyText amount={repayPreview.penalty_allocated} className="font-semibold text-danger" />
                  </div>
                  <div>
                    <span className="text-[var(--muted-ink)] font-sans">Interest Paid:</span>{' '}
                    <MoneyText amount={repayPreview.interest_allocated} className="font-semibold text-[var(--ink)]" />
                  </div>
                  <div>
                    <span className="text-[var(--muted-ink)] font-sans">Principal Paid:</span>{' '}
                    <MoneyText amount={repayPreview.principal_allocated} className="font-semibold text-[var(--ink)]" />
                  </div>
                  <div>
                    <span className="text-[var(--muted-ink)] font-sans">Prepayment Applied:</span>{' '}
                    <MoneyText amount={repayPreview.prepayment_principal} className="font-semibold text-[var(--primary)]" />
                  </div>
                </div>

                <div className="pt-2 border-t border-[var(--border)] flex justify-between text-xs">
                  <span className="text-[var(--muted-ink)]">Principal Balance After:</span>
                  <MoneyText amount={repayPreview.remaining_principal_after} className="font-mono font-bold text-[var(--ink)]" />
                </div>

                {repayPreview.is_loan_fully_paid && (
                  <div className="text-[11px] font-semibold text-[var(--primary)] bg-[var(--surface-muted)] p-1.5 rounded text-center">
                    [FULL SETTLEMENT] Loan will be closed with zero outstanding balance.
                  </div>
                )}
              </div>
            )}

            {repayError && (
              <p className="text-xs text-danger">{repayError}</p>
            )}

            <div className="flex justify-end gap-3 pt-3 border-t border-[var(--border)]">
              <Button variant="secondary" onClick={() => setIsRepayOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                disabled={!repayPreview || repayMutation.isPending}
                onClick={() => repayMutation.mutate()}
              >
                {repayMutation.isPending ? 'Recording...' : 'Confirm Repayment'}
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* WRITE-OFF DIALOG (Screen 8 requirement) */}
      {isWriteOffOpen && (
        <Dialog
          isOpen={true}
          onClose={() => setIsWriteOffOpen(false)}
          title="Write Off Loan (Admin Only)"
        >
          <div className="space-y-4 text-xs">
            <p className="text-[var(--ink)]">
              Writing off overdue loan <strong className="font-mono">{loan.loan_number}</strong> for{' '}
              <strong>{loan.member_name}</strong>.
            </p>

            <div className="p-3 bg-danger/10 border border-danger/30 rounded text-xs space-y-1">
              <div className="flex justify-between">
                <span>Outstanding Principal to Write Off:</span>
                <MoneyText
                  amount={summary?.outstanding_principal || loan.principal}
                  className="font-bold font-mono text-danger"
                />
              </div>
              <p className="text-[10px] text-danger mt-1">
                This posts a bad-debt loss to Loan Write-offs (Account 5010) and permanently retires the loan asset.
              </p>
            </div>

            <div>
              <label htmlFor="write-off-reason" className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                Formal Reason for Write-Off *
              </label>
              <Input
                id="write-off-reason"
                aria-label="Formal Reason for Write-Off"
                value={writeOffReason}
                onChange={(e) => {
                  setWriteOffReason(e.target.value);
                  if (writeOffError) setWriteOffError(null);
                }}
                placeholder="e.g. Borrower uncontactable for 180 days; collateral unrecoverable"
                error={writeOffError || undefined}
              />
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-[var(--border)]">
              <Button variant="secondary" onClick={() => setIsWriteOffOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={writeOffMutation.isPending || !writeOffReason.trim()}
                onClick={() => writeOffMutation.mutate()}
              >
                {writeOffMutation.isPending ? 'Processing Write-off...' : 'Confirm Write-Off'}
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* REJECT MODAL */}
      {isRejectOpen && (
        <Dialog
          isOpen={true}
          onClose={() => setIsRejectOpen(false)}
          title="Reject Loan Application"
        >
          <div className="space-y-4 text-xs">
            <p className="text-[var(--ink)]">
              Rejecting loan <strong className="font-mono">{loan.loan_number}</strong>. Please provide a formal reason:
            </p>

            <div>
              <label htmlFor="rejection-reason" className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                Rejection Reason *
              </label>
              <Input
                id="rejection-reason"
                aria-label="Rejection Reason"
                value={rejectionReason}
                onChange={(e) => {
                  setRejectionReason(e.target.value);
                  if (rejectionError) setRejectionError(null);
                }}
                placeholder="Reason for rejection"
                error={rejectionError || undefined}
              />
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-[var(--border)]">
              <Button variant="secondary" onClick={() => setIsRejectOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={rejectMutation.isPending}
                onClick={() => {
                  if (!rejectionReason.trim() || rejectionReason.trim().length < 3) {
                    setRejectionError('Rejection reason must be at least 3 characters.');
                    return;
                  }
                  rejectMutation.mutate(rejectionReason.trim());
                }}
              >
                {rejectMutation.isPending ? 'Rejecting...' : 'Confirm Rejection'}
              </Button>
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
};
