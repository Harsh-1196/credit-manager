import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { MoneyText } from '../../components/ui/MoneyText';
import {
  Calendar,
  RotateCcw,
  Sparkles,
  Users,
  CheckCircle2,
  AlertCircle,
  BookOpen,
  Plus,
  FileSpreadsheet,
} from 'lucide-react';

interface GroupMeetingsTabProps {
  groupId: string;
}

export const GroupMeetingsTab: React.FC<GroupMeetingsTabProps> = ({ groupId }) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canManage = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';

  const [isGenerateDuesOpen, setIsGenerateDuesOpen] = useState(false);
  const [isScheduleMeetingOpen, setIsScheduleMeetingOpen] = useState(false);
  const [newMeetingDate, setNewMeetingDate] = useState(() => new Date().toISOString().substring(0, 10));
  const [newMeetingAgenda, setNewMeetingAgenda] = useState('Monthly assembly & batch collections');
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const [periodInput, setPeriodInput] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generateSuccess, setGenerateSuccess] = useState<string | null>(null);

  const {
    data: meetings,
    isLoading: isMeetingsLoading,
    isError: isMeetingsError,
    error: meetingsError,
    refetch: refetchMeetings,
  } = useQuery({
    queryKey: ['group-meetings', groupId],
    queryFn: () => api.meetings.list(groupId),
    enabled: !!groupId,
  });

  const {
    data: ledgerData,
    isLoading: isLedgerLoading,
  } = useQuery({
    queryKey: ['group-ledger', groupId],
    queryFn: () => api.ledger.getGroupLedger(groupId),
    enabled: !!groupId,
  });

  const scheduleMutation = useMutation({
    mutationFn: () =>
      api.meetings.create(groupId, {
        meeting_date: newMeetingDate,
        agenda: newMeetingAgenda,
      }),
    onSuccess: () => {
      setIsScheduleMeetingOpen(false);
      setScheduleError(null);
      queryClient.invalidateQueries({ queryKey: ['group-meetings', groupId] });
    },
    onError: (err) => {
      if (err instanceof ApiException) {
        setScheduleError(err.message);
      } else {
        setScheduleError('Failed to schedule meeting.');
      }
    },
  });

  const generateMutation = useMutation({
    mutationFn: (period: string) => api.savings.generateSavingsDues(groupId, period),
    onSuccess: (dues) => {
      setGenerateSuccess(`Generated monthly dues for ${dues.length} active member(s).`);
      setGenerateError(null);
      queryClient.invalidateQueries({ queryKey: ['group-savings-dues', groupId] });
    },
    onError: (err) => {
      if (err instanceof ApiException) {
        setGenerateError(err.message);
      } else {
        setGenerateError('Failed to generate monthly dues.');
      }
      setGenerateSuccess(null);
    },
  });

  const handleGenerate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!periodInput) return;
    generateMutation.mutate(periodInput);
  };

  const handleScheduleMeeting = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMeetingDate) return;
    scheduleMutation.mutate();
  };

  if (isMeetingsLoading || isLedgerLoading) {
    return (
      <div className="space-y-4">
        <Skeleton height="5rem" width="100%" />
        <Skeleton height="12rem" width="100%" />
      </div>
    );
  }

  if (isMeetingsError) {
    return (
      <div className="py-8">
        <EmptyState
          title="Error Loading Meetings"
          description={
            meetingsError instanceof ApiException
              ? meetingsError.message
              : 'Failed to retrieve meeting registers.'
          }
          action={
            <Button variant="secondary" onClick={() => refetchMeetings()}>
              <RotateCcw className="w-4 h-4 mr-1.5" />
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  const meetingList = meetings || [];
  const trialBalance = ledgerData?.trial_balance || [];

  return (
    <div className="space-y-6">
      {/* Action Header */}
      <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 shadow-sm">
        <div>
          <h2 className="font-serif text-lg font-bold text-[var(--ink)]">
            Meetings & Periodic Cycles
          </h2>
          <p className="text-xs text-[var(--muted-ink)] mt-0.5">
            Track assembly meetings, record multi-member collections, and run monthly billing cycles.
          </p>
        </div>

        {canManage && (
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="secondary" onClick={() => setIsGenerateDuesOpen(true)}>
              <Sparkles className="w-4 h-4 mr-1.5" />
              Generate Savings Dues
            </Button>
            <Button variant="primary" onClick={() => setIsScheduleMeetingOpen(true)}>
              <Plus className="w-4 h-4 mr-1.5" />
              Schedule Meeting
            </Button>
          </div>
        )}
      </div>

      {/* Group Ledger Summary Banner */}
      {ledgerData && (
        <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)]">
          <div className="flex justify-between items-center mb-4 pb-2 border-b border-[var(--border)]">
            <div>
              <h3 className="font-serif text-base font-bold text-[var(--ink)] flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-[var(--primary)]" />
                Group General Ledger & Trial Balance
              </h3>
              <p className="text-xs text-[var(--muted-ink)]">
                Double-entry chart of accounts snapshot (Total debits == Total credits:{' '}
                {ledgerData.is_balanced ? 'Balanced' : 'Unbalanced'}).
              </p>
            </div>
            <div>
              <StatusChip variant={ledgerData.is_balanced ? 'success' : 'danger'}>
                {ledgerData.is_balanced ? 'TRIAL BALANCE: BALANCED' : 'UNBALANCED'}
              </StatusChip>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[var(--surface-sunken)] border-b border-[var(--border)] text-[var(--muted-ink)] font-mono uppercase tracking-wider text-[11px]">
                  <th className="py-2.5 px-3">Account Code</th>
                  <th className="py-2.5 px-3">Account Title</th>
                  <th className="py-2.5 px-3">Classification</th>
                  <th className="py-2.5 px-3 text-right">Debit Total (₹)</th>
                  <th className="py-2.5 px-3 text-right">Credit Total (₹)</th>
                  <th className="py-2.5 px-3 text-right">Net Balance (₹)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {trialBalance.map((item) => (
                  <tr key={item.account_id} className="hover:bg-[var(--surface-sunken)]/40">
                    <td className="py-2.5 px-3 font-mono font-medium text-[var(--ink)]">
                      {item.account_code}
                    </td>
                    <td className="py-2.5 px-3 text-[var(--ink)] font-medium">
                      {item.account_name}
                    </td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-[10px] uppercase px-1.5 py-0.5 rounded bg-[var(--surface-sunken)] text-[var(--muted-ink)] border border-[var(--border)]">
                        {item.account_type}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono tabular-nums text-[var(--ink)]">
                      <MoneyText amount={item.total_debit} />
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono tabular-nums text-[var(--ink)]">
                      <MoneyText amount={item.total_credit} />
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono tabular-nums font-semibold text-[var(--ink)]">
                      <MoneyText amount={item.net_balance} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Meetings Register List */}
      <div className="bg-[var(--surface)] rounded border border-[var(--border)] overflow-hidden shadow-sm">
        <div className="p-4 border-b border-[var(--border)] flex justify-between items-center">
          <h3 className="font-serif text-base font-bold text-[var(--ink)]">
            Assembly Meetings Register
          </h3>
          <span className="text-xs text-[var(--muted-ink)] font-mono">
            {meetingList.length} Meeting(s) Logged
          </span>
        </div>

        {meetingList.length === 0 ? (
          <div className="p-8 text-center text-xs text-[var(--muted-ink)]">
            <Calendar className="w-8 h-8 text-[var(--muted-ink)] mx-auto mb-2 opacity-50" />
            No meetings have been logged for this group yet. Click &quot;Schedule Meeting&quot; above to create one.
          </div>
        ) : (
          <div className="divide-y divide-[var(--border)]">
            {meetingList.map((m) => (
              <div
                key={m.id}
                className="p-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 text-xs hover:bg-[var(--surface-sunken)]/40 transition-colors"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-[var(--ink)] text-sm">
                      {m.meeting_date}
                    </span>
                    <StatusChip variant={m.status === 'HELD' ? 'success' : 'neutral'}>
                      {m.status}
                    </StatusChip>
                  </div>
                  <div className="text-[var(--muted-ink)] mt-0.5">
                    {m.agenda || 'Regular monthly assembly and collections'}
                  </div>
                </div>

                <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-end">
                  <span className="text-[var(--muted-ink)] font-mono text-[11px] flex items-center gap-1">
                    <Users className="w-3.5 h-3.5" />
                    {m.attendance_count} Present
                  </span>

                  <Link to={`/meetings/${m.id}/collection`}>
                    <Button
                      variant={m.status === 'SCHEDULED' ? 'primary' : 'secondary'}
                      size="sm"
                      className="gap-1.5"
                    >
                      <FileSpreadsheet className="w-3.5 h-3.5" />
                      {m.status === 'SCHEDULED' ? 'Record Collections' : 'View Sheet'}
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Schedule Meeting Modal */}
      {isScheduleMeetingOpen && (
        <Dialog
          isOpen={true}
          onClose={() => {
            setIsScheduleMeetingOpen(false);
            setScheduleError(null);
          }}
          title="Schedule New Assembly Meeting"
          description="Convene a scheduled group assembly for attendance and periodic collections."
        >
          {scheduleError && (
            <div className="mb-4 p-3 bg-danger/10 border border-danger/20 rounded flex items-start gap-2 text-xs text-danger">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{scheduleError}</span>
            </div>
          )}

          <form onSubmit={handleScheduleMeeting} className="space-y-4 text-xs">
            <div>
              <label className="block text-xs font-medium text-[var(--ink)] mb-1">
                Meeting Date *
              </label>
              <Input
                type="date"
                value={newMeetingDate}
                onChange={(e) => setNewMeetingDate(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[var(--ink)] mb-1">
                Agenda / Purpose
              </label>
              <Input
                value={newMeetingAgenda}
                onChange={(e) => setNewMeetingAgenda(e.target.value)}
                placeholder="e.g. Monthly savings, EMI repayments & loan review"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-[var(--border)]">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setIsScheduleMeetingOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={scheduleMutation.isPending}
              >
                {scheduleMutation.isPending ? 'Scheduling...' : 'Schedule Meeting'}
              </Button>
            </div>
          </form>
        </Dialog>
      )}

      {/* Generate Monthly Dues Modal */}
      {isGenerateDuesOpen && (
        <Dialog
          isOpen={true}
          onClose={() => {
            setIsGenerateDuesOpen(false);
            setGenerateError(null);
            setGenerateSuccess(null);
          }}
          title="Generate Monthly Savings Dues"
          description="Compute and attach mandatory savings dues for all active group members for a billing cycle."
        >
          {generateError && (
            <div className="mb-4 p-3 bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded flex items-start gap-2 text-xs text-[var(--danger)]">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{generateError}</span>
            </div>
          )}

          {generateSuccess && (
            <div className="mb-4 p-3 bg-[var(--success)]/10 border border-[var(--success)]/20 rounded flex items-start gap-2 text-xs text-[var(--success)]">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{generateSuccess}</span>
            </div>
          )}

          <form onSubmit={handleGenerate} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-[var(--ink)] mb-1">
                Billing Period (YYYY-MM)
              </label>
              <Input
                value={periodInput}
                onChange={(e) => setPeriodInput(e.target.value)}
                placeholder="2025-03"
                pattern="^\d{4}-\d{2}$"
                required
              />
              <p className="text-[11px] text-[var(--muted-ink)] mt-1">
                Dues are generated only for members in ACTIVE status who do not already have dues for this period.
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-[var(--border)]">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setIsGenerateDuesOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                disabled={generateMutation.isPending}
              >
                {generateMutation.isPending ? 'Generating...' : 'Generate Dues'}
              </Button>
            </div>
          </form>
        </Dialog>
      )}
    </div>
  );
};
