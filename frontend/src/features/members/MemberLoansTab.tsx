import React from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../lib/api/client';
import type { LoanResponse } from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { MoneyText } from '../../components/ui/MoneyText';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { PlusCircle, Eye } from 'lucide-react';

interface MemberLoansTabProps {
  memberId: string;
  shgId: string;
  memberName: string;
}

export const MemberLoansTab: React.FC<MemberLoansTabProps> = ({
  memberId,
  shgId,
  memberName,
}) => {
  const {
    data: loans,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ['member-loans', memberId],
    queryFn: () => api.loans.list({ member_id: memberId }),
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="bg-[var(--surface)] p-8 rounded border border-[var(--border)] text-center">
        <p className="text-xs text-danger mb-3">Failed to load member loan register.</p>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Apply Action */}
      <div className="flex items-center justify-between bg-[var(--surface)] p-4 rounded border border-[var(--border)]">
        <div>
          <h3 className="font-serif text-base font-semibold text-[var(--ink)]">
            Member Loans & Credit Record
          </h3>
          <p className="text-xs text-[var(--muted-ink)]">
            Active and historical credit applications for {memberName}.
          </p>
        </div>
        <Link to={`/loans/apply?group_id=${shgId}&member_id=${memberId}`}>
          <Button variant="primary" size="sm">
            <PlusCircle className="w-3.5 h-3.5 mr-1.5" />
            Apply for Loan
          </Button>
        </Link>
      </div>

      {loans && loans.length === 0 ? (
        <EmptyState
          title="No Loans Found"
          description={`${memberName} has not submitted any loan applications yet.`}
          action={
            <Link to={`/loans/apply?group_id=${shgId}&member_id=${memberId}`}>
              <Button variant="secondary" size="sm">
                Create First Loan Application
              </Button>
            </Link>
          }
        />
      ) : (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-[var(--surface-muted)] text-[var(--muted-ink)] border-b border-[var(--border)] font-semibold uppercase text-[10px] tracking-wider">
                  <th className="py-2.5 px-3">Loan #</th>
                  <th className="py-2.5 px-3 text-right">Principal</th>
                  <th className="py-2.5 px-3">Tenure & Rate</th>
                  <th className="py-2.5 px-3">Purpose</th>
                  <th className="py-2.5 px-3">Applied Date</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)] font-mono">
                {loans?.map((loan: LoanResponse) => (
                  <tr
                    key={loan.id}
                    className="hover:bg-[var(--surface-muted)]/50 transition-colors"
                  >
                    <td className="py-2.5 px-3 font-semibold text-[var(--ink)]">
                      <Link
                        to={`/loans/${loan.id}`}
                        className="text-[var(--primary)] hover:underline"
                      >
                        {loan.loan_number}
                      </Link>
                    </td>
                    <td className="py-2.5 px-3 text-right font-medium text-[var(--ink)] tabular-nums">
                      <MoneyText amount={loan.principal} />
                    </td>
                    <td className="py-2.5 px-3 text-[var(--ink)] font-sans">
                      {loan.tenure_months}m @ {loan.interest_rate}% ({loan.interest_type})
                    </td>
                    <td className="py-2.5 px-3 text-[var(--muted-ink)] font-sans max-w-xs truncate">
                      {loan.purpose}
                    </td>
                    <td className="py-2.5 px-3 text-[var(--muted-ink)]">
                      {loan.applied_at ? loan.applied_at.split('T')[0] : 'Draft'}
                    </td>
                    <td className="py-2.5 px-3 font-sans">
                      <StatusChip status={loan.status} />
                    </td>
                    <td className="py-2.5 px-3 text-right font-sans">
                      <Link to={`/loans/${loan.id}`}>
                        <Button variant="ghost" size="sm">
                          <Eye className="w-3.5 h-3.5 mr-1" />
                          View
                        </Button>
                      </Link>
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
