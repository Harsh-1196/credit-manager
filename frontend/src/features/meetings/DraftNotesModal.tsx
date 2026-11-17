import React, { useState } from 'react';
import { api, ApiException } from '../../lib/api/client';
import type { DraftCollectionResponse } from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import {
  Sparkles,
  X,
  AlertTriangle,
  FileText,
  UserX,
  ArrowRight,
} from 'lucide-react';

interface DraftNotesModalProps {
  isOpen: boolean;
  onClose: () => void;
  meetingId: string;
  shgName?: string;
  onApplyDraft: (draft: DraftCollectionResponse) => void;
}

const SAMPLE_NOTES = `Radha paid 500 savings and 1100 emi.
Sunita deposited 500 savings.
Geeta was absent today.
Meera paid 500 savings and 50 fine.
Pooja paid 500 savings and 2000 emi.`;

export const DraftNotesModal: React.FC<DraftNotesModalProps> = ({
  isOpen,
  onClose,
  meetingId,
  shgName,
  onApplyDraft,
}) => {
  const [notes, setNotes] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftResult, setDraftResult] = useState<DraftCollectionResponse | null>(null);

  if (!isOpen) return null;

  const handleExtract = async () => {
    if (!notes.trim() || isLoading) return;

    setError(null);
    setIsLoading(true);

    try {
      const result = await api.ai.draftCollection({
        meeting_id: meetingId,
        notes: notes.trim(),
      });
      setDraftResult(result);
    } catch (err: unknown) {
      const msg =
        err instanceof ApiException ? err.message : 'Failed to extract draft collections from notes.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleApply = () => {
    if (!draftResult) return;
    onApplyDraft(draftResult);
    onClose();
  };

  const handleReset = () => {
    setDraftResult(null);
    setError(null);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-[1px]"
      aria-modal="true"
      role="dialog"
      aria-label="Draft Collection from Notes"
    >
      <div className="bg-[var(--surface)] text-[var(--ink)] rounded-lg shadow-xl border border-[var(--border)] w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="p-4 border-b border-[var(--border)] flex items-center justify-between bg-[var(--surface-sunken)]">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[var(--primary)] text-white flex items-center justify-center shadow-sm">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold tracking-tight text-[var(--ink)]">
                Draft Collection from Notes
              </h2>
              <p className="text-[10px] text-[var(--muted-ink)]">
                AI extraction &bull; Draft only &bull; Requires human review
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            title="Close dialog"
            aria-label="Close dialog"
            className="h-8 w-8 p-0 text-[var(--muted-ink)]"
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Notice Disclaimer */}
        <div className="px-4 py-2 bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200 dark:border-amber-900/60 text-[11px] text-amber-900 dark:text-amber-200 flex items-start gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
          <span>
            <strong>Human Review Required:</strong> Extracted figures will pre-fill the collection table. Nothing is posted to the ledger until you review and confirm in the final step.
          </span>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!draftResult ? (
            <>
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label htmlFor="notes-textarea" className="text-xs font-medium text-[var(--ink)]">
                    Paste Meeting Notes or Dictation:
                  </label>
                  <button
                    type="button"
                    onClick={() => setNotes(SAMPLE_NOTES)}
                    className="text-[11px] text-[var(--primary)] hover:underline flex items-center gap-1"
                  >
                    <FileText className="w-3 h-3" /> Insert sample notes
                  </button>
                </div>
                <textarea
                  id="notes-textarea"
                  rows={7}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="e.g. Radha paid 500 savings and 1100 emi. Sunita gave 500. Geeta was absent. Meera paid 500 and 50 fine..."
                  className="w-full rounded-md border border-[var(--border)] bg-[var(--surface-sunken)] p-3 text-xs text-[var(--ink)] placeholder:text-[var(--muted-ink)] font-sans focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
                />
              </div>

              {error && (
                <div className="p-3 rounded border border-danger/30 bg-danger/10 text-danger text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}
            </>
          ) : (
            <div className="space-y-3">
              {/* Draft Extraction Summary */}
              <div className="p-3 rounded border border-[var(--border)] bg-[var(--surface-sunken)] flex items-center justify-between text-xs">
                <div>
                  <div className="font-semibold text-[var(--ink)]">
                    Extraction Completed for {shgName || draftResult.shg_name}
                  </div>
                  <div className="text-[11px] text-[var(--muted-ink)]">
                    Matched {draftResult.items.length} members &bull; Total Draft: ₹{draftResult.total_collected_draft}
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={handleReset} className="text-xs">
                  Edit Notes
                </Button>
              </div>

              {/* Unmatched or Ambiguous warnings */}
              {draftResult.unmatched_items && draftResult.unmatched_items.length > 0 && (
                <div className="p-3 rounded border border-amber-300 bg-amber-50 dark:bg-amber-950/40 text-xs text-amber-900 dark:text-amber-200 space-y-1.5">
                  <div className="font-semibold flex items-center gap-1.5">
                    <UserX className="w-4 h-4 text-amber-700" />
                    Unmatched Notes ({draftResult.unmatched_items.length}) - Require Manual Entry:
                  </div>
                  <ul className="list-disc pl-5 space-y-0.5 text-[11px]">
                    {draftResult.unmatched_items.map((item, idx) => (
                      <li key={idx}>
                        <span className="font-mono">"{item.raw_text}"</span>
                        {item.detected_amount && (
                          <span className="ml-1 text-[var(--muted-ink)]">
                            (Detected ₹{item.detected_amount})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {draftResult.ambiguous_members && draftResult.ambiguous_members.length > 0 && (
                <div className="p-3 rounded border border-amber-300 bg-amber-50 dark:bg-amber-950/40 text-xs text-amber-900 dark:text-amber-200 space-y-1.5">
                  <div className="font-semibold flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4 text-amber-700" />
                    Ambiguous Member Names ({draftResult.ambiguous_members.length}) - Skipped Auto-fill:
                  </div>
                  <ul className="list-disc pl-5 space-y-0.5 text-[11px]">
                    {draftResult.ambiguous_members.map((name, idx) => (
                      <li key={idx}>
                        Multiple members match <strong className="font-mono">"{name}"</strong>. Please fill manually.
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Extracted Matched Items Table */}
              <div className="border border-[var(--border)] rounded overflow-hidden">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[var(--surface-sunken)] border-b border-[var(--border)] text-[10px] text-[var(--muted-ink)] uppercase font-semibold">
                    <tr>
                      <th className="py-1.5 px-3">Member</th>
                      <th className="py-1.5 px-2">Attendance</th>
                      <th className="py-1.5 px-2 text-right">Savings</th>
                      <th className="py-1.5 px-2 text-right">EMI</th>
                      <th className="py-1.5 px-2 text-right">Fine</th>
                      <th className="py-1.5 px-3 text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)]">
                    {draftResult.items.map((item) => (
                      <tr key={item.member_id} className="hover:bg-[var(--surface-sunken)]/50">
                        <td className="py-1.5 px-3 font-medium text-[var(--ink)]">
                          {item.member_name}
                        </td>
                        <td className="py-1.5 px-2 font-mono text-[11px]">
                          {item.attendance === 'ABSENT' ? (
                            <span className="text-danger font-semibold">ABSENT</span>
                          ) : (
                            <span className="text-emerald-700">PRESENT</span>
                          )}
                        </td>
                        <td className="py-1.5 px-2 text-right font-mono">₹{item.savings_amount}</td>
                        <td className="py-1.5 px-2 text-right font-mono">₹{item.loan_repayment_amount}</td>
                        <td className="py-1.5 px-2 text-right font-mono">₹{item.fine_amount}</td>
                        <td className="py-1.5 px-3 text-right font-mono font-semibold text-[var(--primary)]">
                          ₹{item.total_amount}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-[var(--border)] bg-[var(--surface-sunken)] flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>

          {!draftResult ? (
            <Button
              variant="primary"
              size="sm"
              onClick={handleExtract}
              disabled={!notes.trim() || isLoading}
            >
              {isLoading ? (
                <span>Extracting...</span>
              ) : (
                <span className="flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5" /> Extract with AI
                </span>
              )}
            </Button>
          ) : (
            <Button variant="primary" size="sm" onClick={handleApply}>
              <span className="flex items-center gap-1.5">
                Apply to Collection Sheet <ArrowRight className="w-3.5 h-3.5" />
              </span>
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};
