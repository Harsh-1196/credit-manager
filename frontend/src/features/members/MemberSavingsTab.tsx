import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { MoneyText } from '../../components/ui/MoneyText';
import { RecordSavingsModal } from '../savings/RecordSavingsModal';
import {
  PiggyBank,
  Plus,
  RotateCcw,
  Clock,
} from 'lucide-react';

interface MemberSavingsTabProps {
  memberId: string;
  memberName: string;
  groupId?: string;
}

export const MemberSavingsTab: React.FC<MemberSavingsTabProps> = ({
  memberId,
  memberName,
}) => {
  const { user } = useAuth();
  const canManageSavings = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';
  const [isRecordModalOpen, setIsRecordModalOpen] = useState(false);

  const {
    data: savingsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['member-savings', memberId],
    queryFn: () => api.savings.getMemberSavings(memberId),
    enabled: !!memberId,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton height="6rem" width="100%" />
        <Skeleton height="12rem" width="100%" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="py-8">
        <EmptyState
          title="Error Loading Savings Data"
          description={
            error instanceof ApiException
              ? error.message
              : 'Failed to retrieve savings dues and balance.'
          }
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              <RotateCcw className="w-4 h-4 mr-1.5" />
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  const dues = savingsData?.dues || [];
  const totalBalance = savingsData?.total_savings_balance || '0.00';

  const getDueStatusVariant = (status: string) => {
    switch (status) {
      case 'PAID':
        return 'success';
      case 'PENDING':
        return 'neutral';
      case 'PARTIAL':
        return 'warning';
      case 'OVERDUE':
        return 'danger';
      default:
        return 'neutral';
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Total Savings & Quick Actions */}
      <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-[var(--surface-sunken)] rounded border border-[var(--border)]">
            <PiggyBank className="w-8 h-8 text-[var(--primary)]" />
          </div>
          <div>
            <span className="text-[10px] font-mono tracking-wider text-[var(--muted-ink)] uppercase">
              Accumulated Member Savings
            </span>
            <div className="font-mono text-2xl font-bold text-[var(--ink)] mt-0.5">
              <MoneyText amount={totalBalance} />
            </div>
          </div>
        </div>

        {canManageSavings && (
          <Button variant="primary" onClick={() => setIsRecordModalOpen(true)}>
            <Plus className="w-4 h-4 mr-1.5" />
            Record Savings Deposit
          </Button>
        )}
      </div>

      {/* Dues & Payment Status Table */}
      <div className="bg-[var(--surface)] rounded border border-[var(--border)] overflow-hidden">
        <div className="p-4 border-b border-[var(--border)] flex justify-between items-center">
          <div>
            <h3 className="font-serif text-base font-bold text-[var(--ink)]">
              Monthly Savings Schedule & Dues
            </h3>
            <p className="text-xs text-[var(--muted-ink)] mt-0.5">
              History of mandatory savings dues generated for each billing cycle.
            </p>
          </div>
        </div>

        {dues.length === 0 ? (
          <div className="p-8 text-center text-xs text-[var(--muted-ink)]">
            <Clock className="w-8 h-8 text-[var(--muted-ink)] mx-auto mb-2 opacity-50" />
            No savings dues recorded for this member yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[var(--surface-sunken)] border-b border-[var(--border)] text-[var(--muted-ink)] font-mono uppercase tracking-wider text-[11px]">
                  <th className="py-2.5 px-4">Period</th>
                  <th className="py-2.5 px-4 text-right">Amount Due (₹)</th>
                  <th className="py-2.5 px-4 text-right">Amount Paid (₹)</th>
                  <th className="py-2.5 px-4 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {dues.map((due) => (
                  <tr key={due.id} className="hover:bg-[var(--surface-sunken)]/40">
                    <td className="py-3 px-4 font-mono font-medium text-[var(--ink)]">
                      {due.period}
                    </td>
                    <td className="py-3 px-4 text-right font-mono tabular-nums text-[var(--ink)]">
                      <MoneyText amount={due.amount_due} />
                    </td>
                    <td className="py-3 px-4 text-right font-mono tabular-nums text-[var(--success)] font-medium">
                      <MoneyText amount={due.amount_paid} />
                    </td>
                    <td className="py-3 px-4 text-center">
                      <StatusChip variant={getDueStatusVariant(due.status) as any}>
                        {due.status}
                      </StatusChip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Record Savings Modal */}
      {canManageSavings && (
        <RecordSavingsModal
          memberId={memberId}
          memberName={memberName}
          isOpen={isRecordModalOpen}
          onClose={() => setIsRecordModalOpen(false)}
          onSuccess={() => refetch()}
        />
      )}
    </div>
  );
};
