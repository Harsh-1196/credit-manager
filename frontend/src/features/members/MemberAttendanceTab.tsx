import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Button } from '../../components/ui/Button';
import { Calendar, RotateCcw, CheckCircle2, Users } from 'lucide-react';

interface MemberAttendanceTabProps {
  memberId: string;
}

export const MemberAttendanceTab: React.FC<MemberAttendanceTabProps> = ({ memberId }) => {
  const {
    data: attendanceData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['member-attendance', memberId],
    queryFn: () => api.meetings.getMemberAttendance(memberId),
    enabled: !!memberId,
  });

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton height="5rem" width="100%" />
        <Skeleton height="14rem" width="100%" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="py-8">
        <EmptyState
          title="Error Loading Attendance"
          description={error instanceof ApiException ? error.message : 'Failed to retrieve member attendance history.'}
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

  const summary = attendanceData?.summary || {
    total_meetings: 0,
    present_count: 0,
    absent_count: 0,
    excused_count: 0,
    attendance_rate: '0.0%',
  };
  const records = attendanceData?.records || [];

  return (
    <div className="space-y-6">
      {/* Attendance Metrics Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)] shadow-sm">
          <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] tracking-wider">
            Attendance Rate
          </span>
          <div className="font-serif text-2xl font-bold text-[var(--primary)] mt-1 font-mono">
            {summary.attendance_rate}
          </div>
          <span className="text-[11px] text-[var(--muted-ink)] mt-0.5 block">
            {summary.present_count} of {summary.total_meetings} assemblies
          </span>
        </div>

        <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)] shadow-sm">
          <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] tracking-wider">
            Total Assemblies
          </span>
          <div className="font-serif text-2xl font-bold text-[var(--ink)] mt-1 font-mono">
            {summary.total_meetings}
          </div>
          <span className="text-[11px] text-[var(--muted-ink)] mt-0.5 block flex items-center gap-1">
            <Calendar className="w-3 h-3" />
            Convened meetings
          </span>
        </div>

        <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)] shadow-sm">
          <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] tracking-wider">
            Present
          </span>
          <div className="font-serif text-2xl font-bold text-[var(--primary)] mt-1 font-mono">
            {summary.present_count}
          </div>
          <span className="text-[11px] text-[var(--muted-ink)] mt-0.5 block flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-[var(--primary)]" />
            In-person presence
          </span>
        </div>

        <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)] shadow-sm">
          <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] tracking-wider">
            Absent / Excused
          </span>
          <div className="font-serif text-2xl font-bold text-danger mt-1 font-mono">
            {summary.absent_count}
          </div>
          <span className="text-[11px] text-[var(--muted-ink)] mt-0.5 block">
            {summary.excused_count} excused leave(s)
          </span>
        </div>
      </div>

      {/* Assembly Attendance History Register */}
      <div className="bg-[var(--surface)] rounded border border-[var(--border)] overflow-hidden shadow-sm">
        <div className="p-4 border-b border-[var(--border)] flex justify-between items-center">
          <div>
            <h3 className="font-serif text-base font-bold text-[var(--ink)] flex items-center gap-2">
              <Users className="w-4 h-4 text-[var(--primary)]" />
              Member Meeting Register
            </h3>
            <p className="text-xs text-[var(--muted-ink)] mt-0.5">
              Attendance records for each scheduled group assembly.
            </p>
          </div>
        </div>

        {records.length === 0 ? (
          <div className="p-8 text-center text-xs text-[var(--muted-ink)]">
            <Calendar className="w-8 h-8 text-[var(--muted-ink)] mx-auto mb-2 opacity-50" />
            No meeting attendance records logged for this member yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-[var(--surface-sunken)] border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase text-[10px] tracking-wider">
                  <th className="py-2.5 px-4 font-mono w-32">Date</th>
                  <th className="py-2.5 px-4">Agenda / Purpose</th>
                  <th className="py-2.5 px-4 w-36 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {records.map((r) => (
                  <tr key={r.meeting_id} className="hover:bg-[var(--surface-sunken)]/40 transition-colors">
                    <td className="py-2.5 px-4 font-mono font-bold text-[var(--ink)]">
                      {r.meeting_date}
                    </td>
                    <td className="py-2.5 px-4 text-[var(--ink)]">
                      {r.agenda || 'Regular monthly assembly and collections'}
                    </td>
                    <td className="py-2.5 px-4 text-center">
                      <StatusChip
                        variant={
                          r.status === 'PRESENT' ? 'success' : r.status === 'EXCUSED' ? 'neutral' : 'danger'
                        }
                      >
                        [{r.status}]
                      </StatusChip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
