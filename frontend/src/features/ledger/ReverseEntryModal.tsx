import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Dialog } from '../../components/ui/Dialog';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { MoneyText } from '../../components/ui/MoneyText';
import { api, ApiException } from '../../lib/api/client';
import { AlertTriangle, Undo2 } from 'lucide-react';

const reverseSchema = z.object({
  reason: z
    .string()
    .min(5, 'Reason must be at least 5 characters explaining the correction')
    .max(500, 'Reason cannot exceed 500 characters'),
});

type ReverseFormData = z.infer<typeof reverseSchema>;

interface ReverseEntryModalProps {
  entryId: string | null;
  entryDate?: string;
  particulars?: string;
  amount?: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const ReverseEntryModal: React.FC<ReverseEntryModalProps> = ({
  entryId,
  entryDate,
  particulars,
  amount,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ReverseFormData>({
    resolver: zodResolver(reverseSchema),
    defaultValues: {
      reason: '',
    },
  });

  const onSubmit = async (data: ReverseFormData) => {
    if (!entryId) return;

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await api.ledger.reverseEntry(entryId, {
        reason: data.reason,
      });

      reset();
      onSuccess();
      onClose();
    } catch (err) {
      if (err instanceof ApiException) {
        setSubmitError(err.message);
      } else {
        setSubmitError('Failed to reverse the journal entry. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title="Reverse Journal Entry"
      description="Post an offsetting mirror entry to rectify an accounting error."
    >
      {submitError && (
        <div className="mb-4 p-3 bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded flex items-start gap-2 text-xs text-[var(--danger)]">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{submitError}</span>
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="bg-[var(--surface)] p-3 rounded border border-[var(--border)] space-y-2 text-xs">
          <div className="flex justify-between">
            <span className="text-[var(--muted-ink)]">Original Date:</span>
            <span className="font-mono text-[var(--ink)]">{entryDate || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--muted-ink)]">Particulars:</span>
            <span className="text-[var(--ink)] font-medium">{particulars || '—'}</span>
          </div>
          {amount && (
            <div className="flex justify-between">
              <span className="text-[var(--muted-ink)]">Amount:</span>
              <span className="font-mono font-medium text-[var(--ink)]">
                <MoneyText amount={amount} />
              </span>
            </div>
          )}
        </div>

        <div className="p-3 bg-[var(--warning)]/10 border border-[var(--warning)]/20 rounded text-xs text-[var(--warning)] flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <strong>Ledger Rule:</strong> Accounting entries are strictly append-only. Reversal
            posts an inverted entry linked to the original. A reversed entry cannot be reversed
            again.
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-[var(--ink)] mb-1">
            Reason for Reversal <span className="text-[var(--danger)]">*</span>
          </label>
          <Input
            placeholder="e.g. Duplicate collection recorded in error"
            {...register('reason')}
            error={errors.reason?.message}
          />
          <p className="text-[11px] text-[var(--muted-ink)] mt-1">
            This reason is recorded permanently in the audit trail and ledger history.
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t border-[var(--border)]">
          <Button type="button" variant="ghost" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" variant="danger" disabled={isSubmitting}>
            {isSubmitting ? (
              'Reversing...'
            ) : (
              <>
                <Undo2 className="w-4 h-4 mr-1.5" />
                Confirm Reversal
              </>
            )}
          </Button>
        </div>
      </form>
    </Dialog>
  );
};
