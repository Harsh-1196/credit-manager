import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { MoneyText } from '../../components/ui/MoneyText';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ReverseEntryModal } from '../ledger/ReverseEntryModal';
import {
  BookOpen,
  Filter,
  RotateCcw,
  Undo2,
} from 'lucide-react';
import type { PassbookEntry } from '../../lib/api/types';

interface MemberPassbookTabProps {
  memberId: string;
  memberName: string;
  shgId: string;
}

export const MemberPassbookTab: React.FC<MemberPassbookTabProps> = ({
  memberId,
  memberName,
}) => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [filterActive, setFilterActive] = useState(false);

  // Reversal modal state
  const [selectedEntry, setSelectedEntry] = useState<PassbookEntry | null>(null);
  const [isReverseModalOpen, setIsReverseModalOpen] = useState(false);

  const {
    data: passbook,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['member-passbook', memberId, filterActive ? fromDate : '', filterActive ? toDate : ''],
    queryFn: () =>
      api.ledger.getMemberPassbook(
        memberId,
        filterActive && fromDate ? fromDate : undefined,
        filterActive && toDate ? toDate : undefined
      ),
    enabled: !!memberId,
  });

  const handleApplyFilter = (e: React.FormEvent) => {
    e.preventDefault();
    setFilterActive(true);
  };

  const handleResetFilter = () => {
    setFromDate('');
    setToDate('');
    setFilterActive(false);
  };

  const handleOpenReverse = (entry: PassbookEntry) => {
    setSelectedEntry(entry);
    setIsReverseModalOpen(true);
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton height="5rem" width="100%" />
        <Skeleton height="15rem" width="100%" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="py-8">
        <EmptyState
          title="Error Loading Passbook"
          description={
            error instanceof ApiException
              ? error.message
              : 'Failed to retrieve the member savings passbook.'
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

  const entries = passbook?.entries || [];

  return (
    <div className="space-y-6">
      {/* Passbook Header & Total Savings Balance */}
      <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <span className="text-[10px] font-mono tracking-wider text-[var(--muted-ink)] uppercase">
            Passbook Account: 2000-{memberId.slice(0, 8)}
          </span>
          <h2 className="font-serif text-xl font-bold text-[var(--ink)]">
            {memberName}&apos;s Savings Ledger
          </h2>
          <p className="text-xs text-[var(--muted-ink)] mt-0.5">
            Individual sub-account for mandatory savings deposits and withdrawals.
          </p>
        </div>

        <div className="bg-[var(--surface-sunken)] px-5 py-3 rounded border border-[var(--border)] text-right min-w-[200px]">
          <span className="text-[10px] font-mono tracking-wider text-[var(--muted-ink)] uppercase block">
            Net Savings Balance
          </span>
          <div className="font-mono text-2xl font-bold text-[var(--ink)] mt-0.5">
            <MoneyText amount={passbook?.total_savings_balance || '0.00'} />
          </div>
        </div>
      </div>

      {/* Date Range Filter Bar */}
      <form
        onSubmit={handleApplyFilter}
        className="bg-[var(--surface)] p-4 rounded border border-[var(--border)] flex flex-wrap items-end gap-3 text-xs"
      >
        <div className="w-40">
          <Input
            label="From Date"
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </div>

        <div className="w-40">
          <Input
            label="To Date"
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </div>

        <div className="flex gap-2">
          <Button type="submit" variant="secondary" size="sm">
            <Filter className="w-3.5 h-3.5 mr-1" />
            Filter
          </Button>
          {filterActive && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleResetFilter}
            >
              Clear
            </Button>
          )}
        </div>
      </form>

      {/* Ruled Ledger Table (Screen 5) */}
      {entries.length === 0 ? (
        <div className="bg-[var(--surface)] p-12 rounded border border-[var(--border)] text-center">
          <BookOpen className="w-10 h-10 text-[var(--muted-ink)] mx-auto mb-3" />
          <h3 className="font-serif text-lg font-bold text-[var(--ink)]">
            No Passbook Entries Found
          </h3>
          <p className="text-xs text-[var(--muted-ink)] max-w-md mx-auto mt-1">
            {filterActive
              ? 'No transactions fall within the selected date range.'
              : 'No savings transactions have been posted to this account yet.'}
          </p>
        </div>
      ) : (
        <div className="bg-[var(--surface)] rounded border border-[var(--border)] overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[var(--surface-sunken)] border-b-2 border-[var(--border)] text-[var(--muted-ink)] font-mono uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4 w-32 border-r border-[var(--border)]">Date</th>
                  <th className="py-3 px-4 border-r border-[var(--border)]">Particulars</th>
                  <th className="py-3 px-4 w-32 text-right border-r border-[var(--border)]">
                    Debit (₹)
                  </th>
                  <th className="py-3 px-4 w-32 text-right border-r border-[var(--border)]">
                    Credit (₹)
                  </th>
                  <th className="py-3 px-4 w-36 text-right border-r border-[var(--border)]">
                    Balance (₹)
                  </th>
                  {isAdmin && <th className="py-3 px-4 w-24 text-center">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {entries.map((entry, idx) => (
                  <tr
                    key={entry.id || idx}
                    className={`hover:bg-[var(--surface-sunken)]/50 transition-colors ${
                      entry.is_reversal ? 'bg-[var(--warning)]/5' : ''
                    }`}
                  >
                    {/* Date */}
                    <td className="py-3 px-4 font-mono text-[var(--muted-ink)] border-r border-[var(--border)] whitespace-nowrap">
                      {entry.entry_date}
                    </td>

                    {/* Particulars */}
                    <td className="py-3 px-4 border-r border-[var(--border)]">
                      <div className="flex items-center gap-2">
                        <span className="text-[var(--ink)] font-medium">
                          {entry.particulars}
                        </span>
                        {entry.is_reversal && (
                          <StatusChip variant="warning">REVERSAL</StatusChip>
                        )}
                      </div>
                    </td>

                    {/* Debit Column (strictly separate column, positive amount or blank) */}
                    <td className="py-3 px-4 text-right font-mono tabular-nums text-[var(--danger)] border-r border-[var(--border)]">
                      {entry.debit ? (
                        <MoneyText amount={entry.debit} />
                      ) : (
                        <span className="text-[var(--muted-ink)]/40">—</span>
                      )}
                    </td>

                    {/* Credit Column (strictly separate column, positive amount or blank) */}
                    <td className="py-3 px-4 text-right font-mono tabular-nums text-[var(--success)] border-r border-[var(--border)]">
                      {entry.credit ? (
                        <MoneyText amount={entry.credit} />
                      ) : (
                        <span className="text-[var(--muted-ink)]/40">—</span>
                      )}
                    </td>

                    {/* Balance Column */}
                    <td className="py-3 px-4 text-right font-mono tabular-nums font-semibold text-[var(--ink)] border-r border-[var(--border)]">
                      <MoneyText amount={entry.balance} />
                    </td>

                    {/* Admin Actions */}
                    {isAdmin && (
                      <td className="py-2 px-3 text-center">
                        {!entry.is_reversal && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-[var(--danger)] hover:bg-[var(--danger)]/10 text-[11px] h-7 px-2"
                            onClick={() => handleOpenReverse(entry)}
                            title="Reverse this journal entry"
                          >
                            <Undo2 className="w-3.5 h-3.5 mr-1" />
                            Reverse
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-3 bg-[var(--surface-sunken)] border-t border-[var(--border)] text-[11px] text-[var(--muted-ink)] flex justify-between items-center">
            <span>
              Member Savings sub-account (2000-series Liability on SHG books). Credit represents
              deposit; Debit represents withdrawal/reversal.
            </span>
            <span className="font-mono">
              Total {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
            </span>
          </div>
        </div>
      )}

      {/* Admin Reversal Modal */}
      {selectedEntry && (
        <ReverseEntryModal
          entryId={selectedEntry.entry_id}
          entryDate={selectedEntry.entry_date}
          particulars={selectedEntry.particulars}
          amount={selectedEntry.credit || selectedEntry.debit}
          isOpen={isReverseModalOpen}
          onClose={() => {
            setIsReverseModalOpen(false);
            setSelectedEntry(null);
          }}
          onSuccess={() => {
            refetch();
          }}
        />
      )}
    </div>
  );
};
