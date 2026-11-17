import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Decimal from 'decimal.js';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Dialog } from '../../components/ui/Dialog';
import { MoneyText } from '../../components/ui/MoneyText';
import { DraftNotesModal } from './DraftNotesModal';
import type {
  CollectionSheetMemberRow,
  AttendanceStatus,
  MeetingBatchCollectionsRequest,
  MeetingBatchCollectionItem,
  DraftCollectionResponse,
} from '../../lib/api/types';
import {
  RotateCcw,
  Printer,
  CheckCircle2,
  AlertCircle,
  ArrowLeft,
  Users,
  Coins,
  ShieldCheck,
  Keyboard,
  FileSpreadsheet,
  Sparkles,
  UserX,
} from 'lucide-react';

interface MemberFormState {
  member_id: string;
  member_name: string;
  attendance_status: AttendanceStatus;
  savings_amount: string;
  loan_repayment_amount: string;
  fine_amount: string;
  active_loan_id?: string | null;
  active_loan_number?: string | null;
}

export const MeetingCollectionPage: React.FC = () => {
  const { id: meetingId } = useParams<{ id: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const canManage = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';

  // Client-generated idempotency key created once when the screen opens
  const [idempotencyKey] = useState<string>(() => {
    return `meeting-batch-${meetingId}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  });

  const [formState, setFormState] = useState<Record<string, MemberFormState>>({});
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<boolean>(false);
  const [announcement, setAnnouncement] = useState<string>('');

  // AI Draft collection states
  const [isDraftNotesOpen, setIsDraftNotesOpen] = useState(false);
  const [aiDraftSummary, setAiDraftSummary] = useState<{
    matchedCount: number;
    totalAmount: string;
    unmatched: string[];
    ambiguous: string[];
  } | null>(null);
  const [aiModifiedCells, setAiModifiedCells] = useState<Set<string>>(new Set());

  const handleApplyDraft = (draft: DraftCollectionResponse) => {
    const updated = { ...formState };
    const modified = new Set<string>();

    draft.items.forEach((item) => {
      if (updated[item.member_id]) {
        updated[item.member_id] = {
          ...updated[item.member_id],
          attendance_status: item.attendance as AttendanceStatus,
          savings_amount: item.savings_amount,
          loan_repayment_amount: updated[item.member_id].active_loan_id ? item.loan_repayment_amount : '0.00',
          fine_amount: item.fine_amount,
        };
        modified.add(`${item.member_id}-savings`);
        if (updated[item.member_id].active_loan_id) {
          modified.add(`${item.member_id}-emi`);
        }
        modified.add(`${item.member_id}-fine`);
        modified.add(`${item.member_id}-attendance`);
      }
    });

    setFormState(updated);
    setAiModifiedCells(modified);
    setAiDraftSummary({
      matchedCount: draft.items.length,
      totalAmount: String(draft.total_collected_draft),
      unmatched: (draft.unmatched_items || []).map((u) => u.raw_text),
      ambiguous: draft.ambiguous_members || [],
    });
    setAnnouncement(
      `AI Draft applied for ${draft.items.length} members (₹${draft.total_collected_draft}). Please review and confirm before posting.`
    );
  };

  // Cell focus tracking for Enter/Arrow key navigation
  const inputRefs = useRef<Record<string, HTMLInputElement | HTMLSelectElement | null>>({});

  // Fetch collection sheet
  const {
    data: sheetData,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['meeting-collection-sheet', meetingId],
    queryFn: () => api.meetings.getCollectionSheet(meetingId!),
    enabled: !!meetingId,
  });

  // Pre-fill form state when collection sheet loads
  useEffect(() => {
    if (sheetData?.members) {
      const initial: Record<string, MemberFormState> = {};
      sheetData.members.forEach((m: CollectionSheetMemberRow) => {
        // Calculate recommended EMI: current emi due + arrears + penalty due
        const totalEmiDue = new Decimal(m.emi_due || '0')
          .plus(new Decimal(m.arrears || '0'))
          .plus(new Decimal(m.penalty_due || '0'))
          .toFixed(2);

        initial[m.member_id] = {
          member_id: m.member_id,
          member_name: m.member_name,
          attendance_status: m.attendance_status || 'PRESENT',
          savings_amount: m.savings_due || '0.00',
          loan_repayment_amount: m.active_loan_id ? totalEmiDue : '0.00',
          fine_amount: m.fines_due || '0.00',
          active_loan_id: m.active_loan_id,
          active_loan_number: m.active_loan_number,
        };
      });
      setFormState(initial);
      setAnnouncement(`Loaded collection sheet with ${sheetData.members.length} members.`);
    }
  }, [sheetData]);

  // Update single field in form state
  const handleFieldChange = (
    memberId: string,
    field: 'attendance_status' | 'savings_amount' | 'loan_repayment_amount' | 'fine_amount',
    value: string
  ) => {
    setFormState((prev) => {
      const current = prev[memberId];
      if (!current) return prev;
      return {
        ...prev,
        [memberId]: {
          ...current,
          [field]: value,
        },
      };
    });
  };

  // Keyboard shortcut: Mark all present
  const handleMarkAllPresent = () => {
    setFormState((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((mid) => {
        next[mid] = { ...next[mid], attendance_status: 'PRESENT' };
      });
      return next;
    });
    setAnnouncement('Marked all members present.');
  };

  // Keyboard shortcut: Fill all dues from collection sheet
  const handleFillAllDues = () => {
    if (!sheetData?.members) return;
    setFormState((prev) => {
      const next = { ...prev };
      sheetData.members.forEach((m: CollectionSheetMemberRow) => {
        const totalEmi = new Decimal(m.emi_due || '0')
          .plus(new Decimal(m.arrears || '0'))
          .plus(new Decimal(m.penalty_due || '0'))
          .toFixed(2);

        if (next[m.member_id]) {
          next[m.member_id] = {
            ...next[m.member_id],
            attendance_status: 'PRESENT',
            savings_amount: m.savings_due || '0.00',
            loan_repayment_amount: m.active_loan_id ? totalEmi : '0.00',
            fine_amount: m.fines_due || '0.00',
          };
        }
      });
      return next;
    });
    setAnnouncement('Filled all dues from scheduled amounts.');
  };

  // Keyboard shortcut: Clear all collections
  const handleClearAll = () => {
    setFormState((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((mid) => {
        next[mid] = {
          ...next[mid],
          savings_amount: '0.00',
          loan_repayment_amount: '0.00',
          fine_amount: '0.00',
        };
      });
      return next;
    });
    setAnnouncement('Cleared all collection amounts to zero.');
  };

  // Global keyboard shortcuts (Alt+P, Alt+F, Alt+C)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && e.key.toLowerCase() === 'p') {
        e.preventDefault();
        handleMarkAllPresent();
      } else if (e.altKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        handleFillAllDues();
      } else if (e.altKey && e.key.toLowerCase() === 'c') {
        e.preventDefault();
        handleClearAll();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [sheetData]);

  // Navigate inputs with Enter and Arrow keys
  const handleInputKeyDown = (
    e: React.KeyboardEvent<HTMLElement>,
    memberIndex: number,
    field: string,
    totalMembers: number
  ) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      // Move to same column in the next row
      const nextMemberIdx = memberIndex + 1 < totalMembers ? memberIndex + 1 : 0;
      const targetRef = inputRefs.current[`${nextMemberIdx}-${field}`];
      targetRef?.focus();
    } else if (e.key === 'ArrowDown' && e.ctrlKey) {
      e.preventDefault();
      const nextMemberIdx = memberIndex + 1 < totalMembers ? memberIndex + 1 : 0;
      inputRefs.current[`${nextMemberIdx}-${field}`]?.focus();
    } else if (e.key === 'ArrowUp' && e.ctrlKey) {
      e.preventDefault();
      const prevMemberIdx = memberIndex - 1 >= 0 ? memberIndex - 1 : totalMembers - 1;
      inputRefs.current[`${prevMemberIdx}-${field}`]?.focus();
    }
  };

  // Live running totals computed strictly with decimal.js
  const runningTotals = useMemo(() => {
    let savings = new Decimal(0);
    let emi = new Decimal(0);
    let fine = new Decimal(0);
    let present = 0;
    let absent = 0;
    let excused = 0;
    let contributing = 0;

    Object.values(formState).forEach((item) => {
      if (item.attendance_status === 'PRESENT') present++;
      else if (item.attendance_status === 'ABSENT') absent++;
      else if (item.attendance_status === 'EXCUSED') excused++;

      const s = new Decimal(item.savings_amount || 0);
      const e = new Decimal(item.loan_repayment_amount || 0);
      const f = new Decimal(item.fine_amount || 0);

      const memberTot = s.plus(e).plus(f);
      if (memberTot.greaterThan(0)) contributing++;

      savings = savings.plus(s);
      emi = emi.plus(e);
      fine = fine.plus(f);
    });

    const grand = savings.plus(emi).plus(fine);

    return {
      presentCount: present,
      absentCount: absent,
      excusedCount: excused,
      contributingCount: contributing,
      totalSavings: savings.toFixed(2),
      totalEmi: emi.toFixed(2),
      totalFine: fine.toFixed(2),
      grandTotal: grand.toFixed(2),
    };
  }, [formState]);

  // Validation errors
  const validationErrors = useMemo(() => {
    const errors: Record<string, string> = {};
    Object.values(formState).forEach((item) => {
      try {
        const s = new Decimal(item.savings_amount || 0);
        const e = new Decimal(item.loan_repayment_amount || 0);
        const f = new Decimal(item.fine_amount || 0);

        if (s.isNegative()) errors[`${item.member_id}-savings`] = 'Savings cannot be negative';
        if (e.isNegative()) errors[`${item.member_id}-emi`] = 'EMI cannot be negative';
        if (f.isNegative()) errors[`${item.member_id}-fine`] = 'Fine cannot be negative';

        if (e.greaterThan(0) && !item.active_loan_id) {
          errors[`${item.member_id}-emi`] = 'Member has no active loan';
        }
      } catch {
        errors[item.member_id] = 'Invalid decimal number';
      }
    });
    return errors;
  }, [formState]);

  const hasErrors = Object.keys(validationErrors).length > 0;

  // Batch collection mutation
  const postMutation = useMutation({
    mutationFn: async (req: MeetingBatchCollectionsRequest) => {
      return api.meetings.recordCollections(meetingId!, req, idempotencyKey);
    },
    onSuccess: (data) => {
      setSubmitSuccess(true);
      setIsConfirmOpen(false);
      setSubmitError(null);
      queryClient.invalidateQueries({ queryKey: ['meeting-collection-sheet', meetingId] });
      queryClient.invalidateQueries({ queryKey: ['group-meetings'] });
      queryClient.invalidateQueries({ queryKey: ['group-ledger'] });
      setAnnouncement(`Successfully posted ₹${data.total_collected} across ${data.journal_entries_count} balanced journal entries.`);
    },
    onError: (err) => {
      if (err instanceof ApiException) {
        setSubmitError(err.message);
      } else {
        setSubmitError('Failed to record batch meeting collections.');
      }
      setIsConfirmOpen(false);
    },
  });

  const handleConfirmPost = () => {
    if (hasErrors || !sheetData) return;

    const collectionsPayload: MeetingBatchCollectionItem[] = Object.values(formState).map((item) => ({
      member_id: item.member_id,
      attendance_status: item.attendance_status,
      savings_amount: item.savings_amount || '0.00',
      loan_repayment_amount: item.loan_repayment_amount || '0.00',
      fine_amount: item.fine_amount || '0.00',
    }));

    postMutation.mutate({
      period: sheetData.period,
      collections: collectionsPayload,
      idempotency_key: idempotencyKey,
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-7xl mx-auto py-6">
        <Skeleton height="4rem" width="100%" />
        <Skeleton height="20rem" width="100%" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="max-w-7xl mx-auto py-12">
        <EmptyState
          title="Error Loading Meeting Collection"
          description={error instanceof ApiException ? error.message : 'Failed to retrieve meeting collection sheet.'}
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

  const members = sheetData?.members || [];
  const totalMembers = members.length;

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-32">
      {/* Screen reader live announcements */}
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>

      {/* Screen Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-[var(--border)] pb-4 gap-4 print:hidden">
        <div className="flex items-center gap-3">
          <Link
            to={`/groups/${sheetData?.shg_id}`}
            className="p-1.5 rounded hover:bg-[var(--surface-sunken)] text-[var(--muted-ink)] hover:text-[var(--ink)]"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-serif text-xl font-bold tracking-tight text-[var(--ink)]">
                Screen 6: Meeting Collections Grid
              </h1>
              <StatusChip variant={sheetData?.status === 'HELD' ? 'success' : 'neutral'}>
                {sheetData?.status}
              </StatusChip>
            </div>
            <p className="text-xs text-[var(--muted-ink)] mt-0.5">
              SHG: <strong className="text-[var(--ink)]">{sheetData?.shg_name}</strong> | Assembly Date:{' '}
              <strong className="text-[var(--ink)] font-mono">{sheetData?.meeting_date}</strong> | Period:{' '}
              <strong className="text-[var(--ink)] font-mono">{sheetData?.period}</strong>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="secondary" size="sm" onClick={() => window.print()} title="Print physical collection sheet">
            <Printer className="w-3.5 h-3.5 mr-1.5" />
            Print Sheet
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleMarkAllPresent}
            title="Shortcut: Alt+P"
          >
            <Users className="w-3.5 h-3.5 mr-1.5" />
            Mark All Present <span className="text-[10px] opacity-60 ml-1 font-mono">[Alt+P]</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleFillAllDues}
            title="Shortcut: Alt+F"
          >
            <Coins className="w-3.5 h-3.5 mr-1.5" />
            Fill Dues <span className="text-[10px] opacity-60 ml-1 font-mono">[Alt+F]</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setIsDraftNotesOpen(true)}
            title="Draft collections from handwritten/dictated notes with AI"
            className="border-[var(--primary)]/40 text-[var(--primary)] hover:bg-[var(--primary)]/10 font-medium"
          >
            <Sparkles className="w-3.5 h-3.5 mr-1.5" />
            Draft from Notes
          </Button>
        </div>
      </div>

      {/* Printable Sheet Header (Visible Only in Print) */}
      <div className="hidden print:block border-b-2 border-black pb-4 mb-4">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-xl font-bold font-serif uppercase tracking-wider">{sheetData?.shg_name}</h1>
            <p className="text-xs font-mono">Assembly Meeting Collections Sheet</p>
          </div>
          <div className="text-right text-xs font-mono">
            <div>Meeting Date: {sheetData?.meeting_date}</div>
            <div>Billing Period: {sheetData?.period}</div>
          </div>
        </div>
      </div>

      {/* Success Notification Banner */}
      {submitSuccess && (
        <div className="p-4 rounded border border-[var(--primary)]/30 bg-[var(--surface-sunken)] flex items-center justify-between text-xs print:hidden">
          <div className="flex items-center gap-2 text-[var(--ink)]">
            <CheckCircle2 className="w-4 h-4 text-[var(--primary)]" />
            <span>
              <strong>Meeting Collections Posted:</strong> All member dues, repayments, and attendance have been
              recorded atomically in balanced double-entry ledger entries.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Link to={`/groups/${sheetData?.shg_id}`}>
              <Button variant="ghost" size="sm">
                Back to Group
              </Button>
            </Link>
          </div>
        </div>
      )}

      {/* Error Alert Banner */}
      {submitError && (
        <div className="p-4 rounded border border-danger/30 bg-danger/10 text-danger flex items-center justify-between text-xs print:hidden">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{submitError}</span>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setSubmitError(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {/* AI Draft Applied Banner */}
      {aiDraftSummary && (
        <div className="p-3.5 rounded-lg border border-[var(--primary)]/30 bg-[var(--surface-sunken)] text-xs text-[var(--ink)] space-y-2 print:hidden shadow-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[var(--primary)] shrink-0" />
              <span>
                <strong>AI Draft Applied:</strong> Pre-filled {aiDraftSummary.matchedCount} member collections (Total: ₹{aiDraftSummary.totalAmount}). AI-modified fields are highlighted below.
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsDraftNotesOpen(true)}
                className="text-xs text-[var(--primary)]"
              >
                Re-draft
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setAiDraftSummary(null)}
                className="text-xs"
              >
                Dismiss Banner
              </Button>
            </div>
          </div>

          {(aiDraftSummary.unmatched.length > 0 || aiDraftSummary.ambiguous.length > 0) && (
            <div className="p-2.5 rounded bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-900/60 text-[11px] text-amber-900 dark:text-amber-200">
              <div className="font-semibold flex items-center gap-1.5 mb-1">
                <UserX className="w-3.5 h-3.5 text-amber-700 shrink-0" />
                Action Required: The following note entries could not be matched automatically and need manual entry:
              </div>
              <ul className="list-disc pl-5 space-y-0.5">
                {aiDraftSummary.unmatched.map((txt, idx) => (
                  <li key={`unm-${idx}`}>
                    Unmatched text: <span className="font-mono">"{txt}"</span>
                  </li>
                ))}
                {aiDraftSummary.ambiguous.map((name, idx) => (
                  <li key={`amb-${idx}`}>
                    Ambiguous name: <span className="font-mono">"{name}"</span> (matches multiple members)
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Keyboard Shortcuts Hint Bar */}
      <div className="bg-[var(--surface)] p-2.5 rounded border border-[var(--border)] flex items-center justify-between text-[11px] text-[var(--muted-ink)] print:hidden">
        <div className="flex items-center gap-2">
          <Keyboard className="w-3.5 h-3.5 text-[var(--primary)]" />
          <span className="font-medium text-[var(--ink)]">Keyboard Operation:</span>
          <span>Tab/Shift+Tab between fields</span>
          <span className="text-[var(--border)]">|</span>
          <span className="font-mono bg-[var(--surface-sunken)] px-1 py-0.5 rounded border border-[var(--border)] text-[var(--ink)]">
            Enter ↵
          </span>
          <span>moves down to same column</span>
          <span className="text-[var(--border)]">|</span>
          <span>2px visible focus ring</span>
        </div>
        <div>
          <span className="font-mono text-[10px] text-[var(--muted-ink)]">
            Idempotency Key: {idempotencyKey.substring(0, 24)}...
          </span>
        </div>
      </div>

      {/* Desktop/Tablet Grid View (≥ 640px) */}
      <div className="hidden sm:block bg-[var(--surface)] rounded border border-[var(--border)] overflow-hidden shadow-sm">
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="bg-[var(--surface-sunken)] text-[var(--muted-ink)] border-b border-[var(--border)] font-semibold uppercase text-[10px] tracking-wider">
              <th className="py-2.5 px-3 w-12 text-center font-mono">#</th>
              <th className="py-2.5 px-4 min-w-[160px]">Member Name</th>
              <th className="py-2.5 px-3 w-32">Attendance</th>
              <th className="py-2.5 px-3 text-right w-36">Savings (₹)</th>
              <th className="py-2.5 px-3 text-right w-44">Loan EMI (₹)</th>
              <th className="py-2.5 px-3 text-right w-32">Fine / Late (₹)</th>
              <th className="py-2.5 px-4 text-right w-36 font-semibold">Row Total (₹)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            {members.map((m, idx) => {
              const rowState = formState[m.member_id] || {
                member_id: m.member_id,
                member_name: m.member_name,
                attendance_status: 'PRESENT',
                savings_amount: '0.00',
                loan_repayment_amount: '0.00',
                fine_amount: '0.00',
              };

              // Compute live row total
              const rowSavings = new Decimal(rowState.savings_amount || 0);
              const rowEmi = new Decimal(rowState.loan_repayment_amount || 0);
              const rowFine = new Decimal(rowState.fine_amount || 0);
              const rowTotal = rowSavings.plus(rowEmi).plus(rowFine).toFixed(2);

              const hasSavingsErr = !!validationErrors[`${m.member_id}-savings`];
              const hasEmiErr = !!validationErrors[`${m.member_id}-emi`];
              const hasFineErr = !!validationErrors[`${m.member_id}-fine`];

              const isSavingsAi = aiModifiedCells.has(`${m.member_id}-savings`);
              const isEmiAi = aiModifiedCells.has(`${m.member_id}-emi`);
              const isFineAi = aiModifiedCells.has(`${m.member_id}-fine`);
              const isAttAi = aiModifiedCells.has(`${m.member_id}-attendance`);
              const isRowAi = isSavingsAi || isEmiAi || isFineAi || isAttAi;

              return (
                <tr
                  key={m.member_id}
                  className={`hover:bg-[var(--surface-sunken)]/50 transition-colors ${
                    rowState.attendance_status === 'ABSENT' ? 'opacity-70 bg-surface-sunken/20' : ''
                  }`}
                >
                  {/* Row Number */}
                  <td className="py-2.5 px-3 text-center font-mono text-[var(--muted-ink)] text-[11px]">
                    {idx + 1}
                  </td>

                  {/* Member Name */}
                  <td className="py-2.5 px-4 font-medium text-[var(--ink)]">
                    <div className="flex flex-col">
                      <div className="flex items-center gap-1.5">
                        <span>{m.member_name}</span>
                        {isRowAi && (
                          <span
                            className="inline-flex items-center gap-0.5 text-[9px] font-mono px-1 py-0.2 rounded bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300"
                            title="Filled by AI Draft from notes"
                          >
                            <Sparkles className="w-2.5 h-2.5 text-purple-600 dark:text-purple-400" />
                            AI
                          </span>
                        )}
                      </div>
                      {m.active_loan_number && (
                        <span className="text-[10px] font-mono text-[var(--primary)] flex items-center gap-1">
                          Loan: {m.active_loan_number}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Attendance Selector */}
                  <td className="py-2 px-3">
                    <select
                      ref={(el) => {
                        inputRefs.current[`${idx}-attendance_status`] = el;
                      }}
                      value={rowState.attendance_status}
                      onChange={(e) =>
                        handleFieldChange(m.member_id, 'attendance_status', e.target.value as AttendanceStatus)
                      }
                      onKeyDown={(e) => handleInputKeyDown(e, idx, 'attendance_status', totalMembers)}
                      className={`w-full text-xs py-1 px-1.5 rounded border bg-[var(--surface)] text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:border-[var(--primary)] font-sans ${
                        isAttAi ? 'border-purple-400 dark:border-purple-600 bg-purple-50/20 dark:bg-purple-950/20' : 'border-[var(--border)]'
                      }`}
                    >
                      <option value="PRESENT">PRESENT</option>
                      <option value="ABSENT">ABSENT</option>
                      <option value="EXCUSED">EXCUSED</option>
                    </select>
                  </td>

                  {/* Savings Input */}
                  <td className="py-2 px-3 text-right">
                    <div className="relative">
                      <input
                        ref={(el) => {
                          inputRefs.current[`${idx}-savings_amount`] = el;
                        }}
                        type="text"
                        inputMode="decimal"
                        value={rowState.savings_amount}
                        onChange={(e) => handleFieldChange(m.member_id, 'savings_amount', e.target.value)}
                        onKeyDown={(e) => handleInputKeyDown(e, idx, 'savings_amount', totalMembers)}
                        className={`w-full text-right font-mono text-xs py-1 px-2 rounded border bg-[var(--surface)] text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:border-[var(--primary)] tabular-nums ${
                          hasSavingsErr
                            ? 'border-danger focus:ring-danger'
                            : isSavingsAi
                            ? 'border-purple-400 dark:border-purple-600 bg-purple-50/20 dark:bg-purple-950/20'
                            : 'border-[var(--border)]'
                        }`}
                        placeholder="0.00"
                      />
                      {m.savings_due !== '0.00' && (
                        <span className="block text-[10px] text-[var(--muted-ink)] text-right font-mono mt-0.5">
                          Due: ₹{m.savings_due}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Loan EMI Input */}
                  <td className="py-2 px-3 text-right">
                    <div className="relative">
                      <input
                        ref={(el) => {
                          inputRefs.current[`${idx}-loan_repayment_amount`] = el;
                        }}
                        type="text"
                        inputMode="decimal"
                        disabled={!m.active_loan_id}
                        value={rowState.loan_repayment_amount}
                        onChange={(e) =>
                          handleFieldChange(m.member_id, 'loan_repayment_amount', e.target.value)
                        }
                        onKeyDown={(e) =>
                          handleInputKeyDown(e, idx, 'loan_repayment_amount', totalMembers)
                        }
                        className={`w-full text-right font-mono text-xs py-1 px-2 rounded border bg-[var(--surface)] text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:border-[var(--primary)] tabular-nums disabled:opacity-40 disabled:bg-[var(--surface-sunken)] ${
                          hasEmiErr
                            ? 'border-danger focus:ring-danger'
                            : isEmiAi
                            ? 'border-purple-400 dark:border-purple-600 bg-purple-50/20 dark:bg-purple-950/20'
                            : 'border-[var(--border)]'
                        }`}
                        placeholder={m.active_loan_id ? '0.00' : 'No Loan'}
                      />
                      {m.active_loan_id ? (
                        <span className="block text-[10px] text-[var(--muted-ink)] text-right font-mono mt-0.5">
                          EMI: ₹{m.emi_due} {m.arrears !== '0.00' && `+ Arr: ₹${m.arrears}`}
                        </span>
                      ) : (
                        <span className="block text-[10px] text-[var(--muted-ink)] text-right mt-0.5">
                          -
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Fine Input */}
                  <td className="py-2 px-3 text-right">
                    <div className="relative">
                      <input
                        ref={(el) => {
                          inputRefs.current[`${idx}-fine_amount`] = el;
                        }}
                        type="text"
                        inputMode="decimal"
                        value={rowState.fine_amount}
                        onChange={(e) => handleFieldChange(m.member_id, 'fine_amount', e.target.value)}
                        onKeyDown={(e) => handleInputKeyDown(e, idx, 'fine_amount', totalMembers)}
                        className={`w-full text-right font-mono text-xs py-1 px-2 rounded border bg-[var(--surface)] text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)] focus:border-[var(--primary)] tabular-nums ${
                          hasFineErr
                            ? 'border-danger focus:ring-danger'
                            : isFineAi
                            ? 'border-purple-400 dark:border-purple-600 bg-purple-50/20 dark:bg-purple-950/20'
                            : 'border-[var(--border)]'
                        }`}
                        placeholder="0.00"
                      />
                      {m.fines_due !== '0.00' && (
                        <span className="block text-[10px] text-danger text-right font-mono mt-0.5">
                          Fine: ₹{m.fines_due}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Live Row Total */}
                  <td className="py-2.5 px-4 text-right font-mono font-bold tabular-nums text-[var(--ink)]">
                    <MoneyText amount={rowTotal} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile Stacked Cards (< 640px) */}
      <div className="block sm:hidden space-y-4">
        {members.map((m, idx) => {
          const rowState = formState[m.member_id] || {
            member_id: m.member_id,
            member_name: m.member_name,
            attendance_status: 'PRESENT',
            savings_amount: '0.00',
            loan_repayment_amount: '0.00',
            fine_amount: '0.00',
          };

          const rowSavings = new Decimal(rowState.savings_amount || 0);
          const rowEmi = new Decimal(rowState.loan_repayment_amount || 0);
          const rowFine = new Decimal(rowState.fine_amount || 0);
          const rowTotal = rowSavings.plus(rowEmi).plus(rowFine).toFixed(2);

          return (
            <div
              key={m.member_id}
              className="bg-[var(--surface)] border border-[var(--border)] rounded p-4 space-y-3 shadow-sm"
            >
              <div className="flex justify-between items-start border-b border-[var(--border)] pb-2">
                <div>
                  <span className="text-[10px] font-mono text-[var(--muted-ink)] mr-1">#{idx + 1}</span>
                  <span className="font-bold text-sm text-[var(--ink)]">{m.member_name}</span>
                  {m.active_loan_number && (
                    <div className="text-[10px] font-mono text-[var(--primary)]">
                      Loan: {m.active_loan_number}
                    </div>
                  )}
                </div>
                <select
                  value={rowState.attendance_status}
                  onChange={(e) =>
                    handleFieldChange(m.member_id, 'attendance_status', e.target.value as AttendanceStatus)
                  }
                  className="text-xs py-1 px-2 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--ink)]"
                >
                  <option value="PRESENT">PRESENT</option>
                  <option value="ABSENT">ABSENT</option>
                  <option value="EXCUSED">EXCUSED</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] mb-1">
                    Savings (Due: ₹{m.savings_due})
                  </label>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={rowState.savings_amount}
                    onChange={(e) => handleFieldChange(m.member_id, 'savings_amount', e.target.value)}
                    className="w-full text-right font-mono text-xs py-1.5 px-2 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--ink)] tabular-nums"
                  />
                </div>

                <div>
                  <label className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] mb-1">
                    Loan EMI {m.active_loan_id && `(Due: ₹${m.emi_due})`}
                  </label>
                  <input
                    type="text"
                    inputMode="decimal"
                    disabled={!m.active_loan_id}
                    value={rowState.loan_repayment_amount}
                    onChange={(e) =>
                      handleFieldChange(m.member_id, 'loan_repayment_amount', e.target.value)
                    }
                    className="w-full text-right font-mono text-xs py-1.5 px-2 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--ink)] tabular-nums disabled:opacity-40"
                    placeholder={m.active_loan_id ? '0.00' : 'None'}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs pt-1">
                <div>
                  <label className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] mb-1">
                    Fine / Late (Due: ₹{m.fines_due})
                  </label>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={rowState.fine_amount}
                    onChange={(e) => handleFieldChange(m.member_id, 'fine_amount', e.target.value)}
                    className="w-full text-right font-mono text-xs py-1.5 px-2 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--ink)] tabular-nums"
                  />
                </div>

                <div className="flex flex-col justify-end text-right">
                  <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                    Row Total
                  </span>
                  <span className="font-mono font-bold text-sm text-[var(--primary)]">
                    <MoneyText amount={rowTotal} />
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Sticky Bottom Footer with Live Running Totals */}
      <div className="fixed bottom-0 left-0 right-0 z-20 bg-[var(--surface)] border-t-2 border-[var(--border)] shadow-2xl px-4 py-3 print:hidden">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Left stats: attendance & breakdown */}
          <div className="flex items-center gap-4 text-xs flex-wrap">
            <div className="flex items-center gap-1.5">
              <Users className="w-4 h-4 text-[var(--primary)]" />
              <span className="text-[var(--ink)] font-medium">
                Attendance: <strong>{runningTotals.presentCount}</strong> / {totalMembers} Present
              </span>
              <span className="text-[10px] text-[var(--muted-ink)]">
                ({runningTotals.absentCount} Absent, {runningTotals.excusedCount} Excused)
              </span>
            </div>

            <div className="hidden lg:flex items-center gap-3 border-l border-[var(--border)] pl-3 text-[11px] font-mono">
              <span className="text-[var(--muted-ink)]">
                Savings: <strong className="text-[var(--ink)]">₹{runningTotals.totalSavings}</strong>
              </span>
              <span className="text-[var(--border)]">•</span>
              <span className="text-[var(--muted-ink)]">
                EMI: <strong className="text-[var(--ink)]">₹{runningTotals.totalEmi}</strong>
              </span>
              <span className="text-[var(--border)]">•</span>
              <span className="text-[var(--muted-ink)]">
                Fines: <strong className="text-[var(--ink)]">₹{runningTotals.totalFine}</strong>
              </span>
            </div>
          </div>

          {/* Right stats: Grand Cash In & Post Action */}
          <div className="flex items-center gap-4 w-full md:w-auto justify-between md:justify-end">
            <div className="text-right">
              <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)] tracking-wider">
                Total Cash In Hand
              </span>
              <MoneyText
                amount={runningTotals.grandTotal}
                className="font-mono text-xl font-bold text-[var(--primary)] tabular-nums"
              />
            </div>

            <Button
              variant="primary"
              disabled={!canManage || hasErrors || postMutation.isPending}
              onClick={() => setIsConfirmOpen(true)}
              className="h-10 px-5 text-sm gap-2"
            >
              <FileSpreadsheet className="w-4 h-4" />
              Review & Post Collections
            </Button>
          </div>
        </div>
      </div>

      {/* Confirmation Step Dialog (SPEC 12.6 requirement) */}
      {isConfirmOpen && (
        <Dialog
          isOpen={true}
          onClose={() => setIsConfirmOpen(false)}
          title="Confirm Meeting Collections & Journal Postings"
          description="Review the double-entry accounting summary before permanently posting."
        >
          <div className="space-y-4 text-xs">
            {/* Amount Restated Banner */}
            <div className="p-4 bg-[var(--surface-sunken)] border border-[var(--border)] rounded text-center space-y-1">
              <span className="text-xs uppercase tracking-wider text-[var(--muted-ink)] font-semibold">
                Grand Total Cash Collected
              </span>
              <div className="font-mono text-2xl font-bold text-[var(--primary)]">
                <MoneyText amount={runningTotals.grandTotal} />
              </div>
              <p className="text-[11px] text-[var(--muted-ink)]">
                From <strong>{runningTotals.contributingCount}</strong> contributing member(s) during assembly on{' '}
                <strong>{sheetData?.meeting_date}</strong>.
              </p>
            </div>

            {/* Double Entry Summary */}
            <div className="space-y-2">
              <h4 className="font-semibold uppercase tracking-wider text-[10px] text-[var(--muted-ink)]">
                Double-Entry Posting Breakdown
              </h4>
              <div className="border border-[var(--border)] rounded overflow-hidden">
                <table className="w-full text-[11px] font-mono border-collapse">
                  <thead className="bg-[var(--surface-sunken)] text-[var(--muted-ink)] border-b border-[var(--border)] font-sans">
                    <tr>
                      <th className="py-1.5 px-2.5 text-left">Account</th>
                      <th className="py-1.5 px-2.5 text-right">Debit (₹)</th>
                      <th className="py-1.5 px-2.5 text-right">Credit (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    <tr>
                      <td className="py-1.5 px-2.5 font-sans font-medium text-[var(--ink)]">
                        1000 - Cash in Hand
                      </td>
                      <td className="py-1.5 px-2.5 text-right font-bold text-[var(--primary)]">
                        <MoneyText amount={runningTotals.grandTotal} />
                      </td>
                      <td className="py-1.5 px-2.5 text-right text-[var(--muted-ink)]">-</td>
                    </tr>
                    {new Decimal(runningTotals.totalSavings).greaterThan(0) && (
                      <tr>
                        <td className="py-1.5 px-2.5 font-sans text-[var(--ink)] pl-4">
                          2000 - Member Savings (Per-Member Sub-Accounts)
                        </td>
                        <td className="py-1.5 px-2.5 text-right text-[var(--muted-ink)]">-</td>
                        <td className="py-1.5 px-2.5 text-right text-[var(--ink)]">
                          <MoneyText amount={runningTotals.totalSavings} />
                        </td>
                      </tr>
                    )}
                    {new Decimal(runningTotals.totalEmi).greaterThan(0) && (
                      <tr>
                        <td className="py-1.5 px-2.5 font-sans text-[var(--ink)] pl-4">
                          1100 / 4000 - Member Loans & Interest Allocated
                        </td>
                        <td className="py-1.5 px-2.5 text-right text-[var(--muted-ink)]">-</td>
                        <td className="py-1.5 px-2.5 text-right text-[var(--ink)]">
                          <MoneyText amount={runningTotals.totalEmi} />
                        </td>
                      </tr>
                    )}
                    {new Decimal(runningTotals.totalFine).greaterThan(0) && (
                      <tr>
                        <td className="py-1.5 px-2.5 font-sans text-[var(--ink)] pl-4">
                          4010 - Late Fine & Penalty Income
                        </td>
                        <td className="py-1.5 px-2.5 text-right text-[var(--muted-ink)]">-</td>
                        <td className="py-1.5 px-2.5 text-right text-[var(--ink)]">
                          <MoneyText amount={runningTotals.totalFine} />
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex items-center gap-1.5 text-[11px] text-[var(--muted-ink)]">
              <ShieldCheck className="w-3.5 h-3.5 text-[var(--primary)] shrink-0" />
              <span>
                Posts <strong>one balanced journal entry per member</strong> atomically. If any member allocation fails,
                the entire batch rolls back safely (all-or-nothing).
              </span>
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-[var(--border)]">
              <Button variant="secondary" onClick={() => setIsConfirmOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                disabled={postMutation.isPending}
                onClick={handleConfirmPost}
              >
                {postMutation.isPending ? 'Posting Collections...' : 'Confirm & Post'}
              </Button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Draft Collection from Notes AI Modal */}
      <DraftNotesModal
        isOpen={isDraftNotesOpen}
        onClose={() => setIsDraftNotesOpen(false)}
        meetingId={meetingId!}
        shgName={sheetData?.shg_name}
        onApplyDraft={handleApplyDraft}
      />
    </div>
  );
};
