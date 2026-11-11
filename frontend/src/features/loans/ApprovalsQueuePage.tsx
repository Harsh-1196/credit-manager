import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import type { LoanResponse, GroupResponse } from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { MoneyText } from '../../components/ui/MoneyText';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import {
  AlertCircle,
  Filter,
  ShieldAlert,
  Eye,
} from 'lucide-react';

export const ApprovalsQueuePage: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');

  // Modals state
  const [approveLoan, setApproveLoan] = useState<LoanResponse | null>(null);
  const [rejectLoan, setRejectLoan] = useState<LoanResponse | null>(null);
  const [rejectionReason, setRejectionReason] = useState<string>('');
  const [rejectionError, setRejectionError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Load groups for filter
  const { data: groupsData } = useQuery({
    queryKey: ['groups', 'list'],
    queryFn: () => api.groups.list({ page_size: 100 }),
  });

  // Load submitted loans
  const {
    data: loans,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['loans', 'approvals-queue', selectedGroupId],
    queryFn: () =>
      api.loans.list({
        group_id: selectedGroupId || undefined,
        status: 'SUBMITTED',
      }),
  });

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: async ({ loanId, version }: { loanId: string; version: number }) => {
      return api.loans.approve(loanId, { version });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loans'] });
      setApproveLoan(null);
      setActionError(null);
    },
    onError: (err: unknown) => {
      if (err instanceof ApiException) {
        setActionError(err.message);
      } else {
        setActionError('Failed to approve loan.');
      }
    },
  });

  // Reject mutation
  const rejectMutation = useMutation({
    mutationFn: async ({
      loanId,
      version,
      reason,
    }: {
      loanId: string;
      version: number;
      reason: string;
    }) => {
      return api.loans.reject(loanId, { version, reason });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loans'] });
      setRejectLoan(null);
      setRejectionReason('');
      setRejectionError(null);
      setActionError(null);
    },
    onError: (err: unknown) => {
      if (err instanceof ApiException) {
        setActionError(err.message);
      } else {
        setActionError('Failed to reject loan.');
      }
    },
  });

  const handleConfirmApprove = () => {
    if (!approveLoan) return;
    approveMutation.mutate({
      loanId: approveLoan.id,
      version: approveLoan.version,
    });
  };

  const handleConfirmReject = () => {
    if (!rejectLoan) return;
    if (!rejectionReason.trim() || rejectionReason.trim().length < 3) {
      setRejectionError('A clear explanation of at least 3 characters is required.');
      return;
    }
    rejectMutation.mutate({
      loanId: rejectLoan.id,
      version: rejectLoan.version,
      reason: rejectionReason.trim(),
    });
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Editorial Header */}
      <div className="border-b border-[var(--border)] pb-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl font-bold tracking-tight text-[var(--ink)]">
            Screen 9: Approvals Queue
          </h1>
          <p className="mt-1 text-sm text-[var(--muted-ink)]">
            Review pending loan applications with strict maker-checker segregation of duties.
          </p>
        </div>
        <Link to="/loans/apply">
          <Button variant="primary">New Loan Application</Button>
        </Link>
      </div>

      {actionError && (
        <div className="p-4 rounded border border-danger/30 bg-surface-sunken flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-danger shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-sm font-semibold text-danger">Action Failed</h4>
            <p className="text-xs text-[var(--ink)] mt-1">{actionError}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => setActionError(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="bg-[var(--surface)] p-3 border border-[var(--border)] rounded flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 max-w-sm flex-1">
          <Filter className="w-4 h-4 text-[var(--muted-ink)] shrink-0" />
          <Select
            aria-label="Filter by group"
            value={selectedGroupId}
            onChange={(e) => setSelectedGroupId(e.target.value)}
            options={[
              { label: 'All Permitted Groups', value: '' },
              ...(groupsData?.items.map((g: GroupResponse) => ({
                label: g.name,
                value: g.id,
              })) || []),
            ]}
          />
        </div>
        <div className="text-xs text-[var(--muted-ink)]">
          {loans ? `${loans.length} pending application(s)` : 'Loading...'}
        </div>
      </div>

      {/* Main Table or Loading/Empty/Error states */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-6 space-y-4">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : isError ? (
          <div className="p-12 text-center">
            <AlertCircle className="w-8 h-8 text-danger mx-auto mb-2" />
            <h3 className="font-serif text-base font-bold text-[var(--ink)]">
              Failed to Load Queue
            </h3>
            <p className="text-xs text-[var(--muted-ink)] mt-1 mb-4">
              An error occurred while fetching pending loan applications.
            </p>
            <Button variant="secondary" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        ) : loans && loans.length === 0 ? (
          <EmptyState
            title="Approvals Queue Clear"
            description="There are currently no submitted loan applications waiting for leader review."
            action={
              <Link to="/loans/apply">
                <Button variant="secondary" size="sm">
                  Apply for a Loan
                </Button>
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-[var(--surface-muted)] text-[var(--muted-ink)] border-b border-[var(--border)] font-semibold uppercase text-[10px] tracking-wider">
                  <th className="py-3 px-4">Loan #</th>
                  <th className="py-3 px-4">Applicant Member</th>
                  <th className="py-3 px-4">Group</th>
                  <th className="py-3 px-4 text-right">Principal</th>
                  <th className="py-3 px-4">Tenure</th>
                  <th className="py-3 px-4">Purpose</th>
                  <th className="py-3 px-4">Maker-Checker Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {loans?.map((loan) => {
                  const canApprove = loan.can_approve ?? true;
                  const note = loan.maker_checker_note;

                  return (
                    <tr
                      key={loan.id}
                      className="hover:bg-[var(--surface-muted)]/50 transition-colors"
                    >
                      <td className="py-3 px-4 font-mono font-medium text-[var(--ink)]">
                        <Link
                          to={`/loans/${loan.id}`}
                          className="text-[var(--primary)] hover:underline inline-flex items-center gap-1"
                        >
                          {loan.loan_number}
                        </Link>
                      </td>
                      <td className="py-3 px-4 text-[var(--ink)] font-medium">
                        {loan.member_name || 'Member'}
                      </td>
                      <td className="py-3 px-4 text-[var(--muted-ink)] font-mono text-[11px]">
                        {groupsData?.items.find((g) => g.id === loan.shg_id)?.name || loan.shg_id.slice(0, 8)}
                      </td>
                      <td className="py-3 px-4 text-right font-mono font-semibold text-[var(--ink)] tabular-nums">
                        <MoneyText amount={loan.principal} />
                      </td>
                      <td className="py-3 px-4 text-[var(--ink)]">
                        {loan.tenure_months} mos @ {loan.interest_rate}% ({loan.interest_type})
                      </td>
                      <td className="py-3 px-4 text-[var(--muted-ink)] max-w-xs truncate">
                        {loan.purpose}
                      </td>
                      <td className="py-3 px-4">
                        {canApprove ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-primary-tint text-primary border border-primary/20">
                            [OK] Ready for Decision
                          </span>
                        ) : (
                          <div className="flex items-start gap-1.5 max-w-xs">
                            <ShieldAlert className="w-3.5 h-3.5 text-warning shrink-0 mt-0.5" />
                            <span className="text-[11px] text-warning font-medium leading-snug">
                              {note || 'Maker cannot approve own application'}
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-2">
                          <Link to={`/loans/${loan.id}`}>
                            <Button
                              variant="ghost"
                              size="sm"
                              title="View Schedule"
                              aria-label={`View schedule for loan ${loan.loan_number}`}
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </Button>
                          </Link>

                          <Button
                            variant="primary"
                            size="sm"
                            disabled={!canApprove || approveMutation.isPending}
                            onClick={() => setApproveLoan(loan)}
                            title={canApprove ? 'Approve Loan' : note || 'Maker cannot approve'}
                          >
                            Approve
                          </Button>

                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={rejectMutation.isPending}
                            onClick={() => {
                              setRejectLoan(loan);
                              setRejectionReason('');
                              setRejectionError(null);
                            }}
                          >
                            Reject
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Confirm Approve Dialog */}
      {approveLoan && (
        <Dialog
          isOpen={true}
          onClose={() => setApproveLoan(null)}
          title="Confirm Loan Approval"
        >
          <div className="space-y-4 text-xs">
            <p className="text-[var(--ink)]">
              You are approving the following loan application under the group's lending policy:
            </p>

            <div className="bg-[var(--surface-muted)] p-3 rounded border border-[var(--border)] space-y-2 font-mono">
              <div className="flex justify-between">
                <span className="text-[var(--muted-ink)]">Loan #:</span>
                <span className="font-semibold text-[var(--ink)]">{approveLoan.loan_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--muted-ink)]">Applicant:</span>
                <span className="text-[var(--ink)]">{approveLoan.member_name || 'Member'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--muted-ink)]">Principal Amount:</span>
                <MoneyText amount={approveLoan.principal} className="font-bold text-[var(--primary)]" />
              </div>
              <div className="flex justify-between">
                <span className="text-[var(--muted-ink)]">Tenure & Rate:</span>
                <span className="text-[var(--ink)]">
                  {approveLoan.tenure_months} months @ {approveLoan.interest_rate}% ({approveLoan.interest_type})
                </span>
              </div>
              <div className="flex justify-between text-[11px]">
                <span className="text-[var(--muted-ink)]">Expected Version:</span>
                <span className="text-[var(--muted-ink)]">v{approveLoan.version} (optimistic lock)</span>
              </div>
            </div>

            <p className="text-[11px] text-[var(--muted-ink)]">
              Approval records your user ID ({approveLoan.loan_number}) in the tamper-evident
              audit log and moves the loan to APPROVED status awaiting disbursement.
            </p>

            <div className="flex justify-end gap-3 pt-3 border-t border-[var(--border)]">
              <Button variant="secondary" onClick={() => setApproveLoan(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                disabled={approveMutation.isPending}
                onClick={handleConfirmApprove}
              >
                {approveMutation.isPending ? 'Approving...' : 'Confirm Approval'}
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Reject Dialog with Mandatory Reason */}
      {rejectLoan && (
        <Dialog
          isOpen={true}
          onClose={() => setRejectLoan(null)}
          title="Reject Loan Application"
        >
          <div className="space-y-4 text-xs">
            <p className="text-[var(--ink)]">
              Rejecting loan <strong className="font-mono">{rejectLoan.loan_number}</strong> for member{' '}
              <strong>{rejectLoan.member_name || 'Member'}</strong>. A reason is required for group
              records and audit transparency.
            </p>

            <div>
              <label htmlFor="queue-rejection-reason" className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                Rejection Reason *
              </label>
              <Input
                id="queue-rejection-reason"
                aria-label="Rejection Reason"
                value={rejectionReason}
                onChange={(e) => {
                  setRejectionReason(e.target.value);
                  if (rejectionError) setRejectionError(null);
                }}
                placeholder="e.g. Insufficient group liquidity, incomplete KYC documentation"
                error={rejectionError || undefined}
              />
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-[var(--border)]">
              <Button variant="secondary" onClick={() => setRejectLoan(null)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={rejectMutation.isPending}
                onClick={handleConfirmReject}
              >
                {rejectMutation.isPending ? 'Rejecting...' : 'Reject Application'}
              </Button>
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
};
