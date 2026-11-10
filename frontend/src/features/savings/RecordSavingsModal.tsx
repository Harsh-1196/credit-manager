import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Dialog } from '../../components/ui/Dialog';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { MoneyText } from '../../components/ui/MoneyText';
import { api, ApiException } from '../../lib/api/client';
import { AlertCircle, CheckCircle2, ArrowRight, ArrowLeft } from 'lucide-react';

const savingsSchema = z.object({
  amount: z.string().refine((val) => {
    const num = Number(val);
    return !isNaN(num) && num > 0;
  }, 'Amount must be greater than zero'),
  period: z
    .string()
    .regex(/^\d{4}-\d{2}$/, 'Period must be in YYYY-MM format (e.g. 2025-03)'),
  collected_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, 'Date must be in YYYY-MM-DD format'),
  fine_amount: z.string().refine((val) => {
    if (!val) return true;
    const num = Number(val);
    return !isNaN(num) && num >= 0;
  }, 'Fine must be non-negative'),
});

type SavingsFormData = z.infer<typeof savingsSchema>;

interface RecordSavingsModalProps {
  memberId: string;
  memberName: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const RecordSavingsModal: React.FC<RecordSavingsModalProps> = ({
  memberId,
  memberName,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [step, setStep] = useState<'form' | 'confirm'>('form');
  const [idempotencyKey, setIdempotencyKey] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const getCurrentPeriod = () => {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    return `${year}-${month}`;
  };

  const getTodayDate = () => {
    const now = new Date();
    return now.toISOString().split('T')[0];
  };

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<SavingsFormData>({
    resolver: zodResolver(savingsSchema),
    defaultValues: {
      amount: '200.00',
      period: getCurrentPeriod(),
      collected_date: getTodayDate(),
      fine_amount: '0.00',
    },
  });

  // Generate unique idempotency key when opening modal
  useEffect(() => {
    if (isOpen) {
      setIdempotencyKey(crypto.randomUUID());
      setStep('form');
      setSubmitError(null);
      reset({
        amount: '200.00',
        period: getCurrentPeriod(),
        collected_date: getTodayDate(),
        fine_amount: '0.00',
      });
    }
  }, [isOpen, reset]);

  const currentValues = watch();

  const handleProceedToConfirm = () => {
    setStep('confirm');
  };

  const handleFinalSubmit = async () => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      await api.savings.collect(
        {
          member_id: memberId,
          amount: currentValues.amount,
          period: currentValues.period,
          entry_date: currentValues.collected_date,
          fine_amount: currentValues.fine_amount || '0.00',
        },
        idempotencyKey
      );

      onSuccess();
      onClose();
    } catch (err) {
      if (err instanceof ApiException) {
        setSubmitError(err.message);
      } else {
        setSubmitError('Failed to record savings collection. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={step === 'form' ? 'Record Savings Deposit' : 'Confirm Savings Deposit'}
      description={
        step === 'form'
          ? `Record a monthly savings collection for ${memberName}.`
          : 'Please review and verify the transaction details before committing to the ledger.'
      }
    >
      {submitError && (
        <div className="mb-4 p-3 bg-[var(--danger)]/10 border border-[var(--danger)]/20 rounded flex items-start gap-2 text-xs text-[var(--danger)]">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{submitError}</span>
        </div>
      )}

      {step === 'form' ? (
        <form onSubmit={handleSubmit(handleProceedToConfirm)} className="space-y-4">
          <div className="bg-[var(--surface)] p-3 rounded border border-[var(--border)] text-xs space-y-1">
            <span className="text-[var(--muted-ink)]">Beneficiary Member:</span>
            <div className="font-semibold text-[var(--ink)]">{memberName}</div>
          </div>

          <div>
            <Input
              label="Deposit Amount (₹) *"
              type="number"
              step="0.01"
              placeholder="200.00"
              {...register('amount')}
              error={errors.amount?.message}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Input
                label="Billing Period (YYYY-MM) *"
                placeholder="2025-03"
                {...register('period')}
                error={errors.period?.message}
              />
            </div>

            <div>
              <Input
                label="Collection Date *"
                type="date"
                {...register('collected_date')}
                error={errors.collected_date?.message}
              />
            </div>
          </div>

          <div>
            <Input
              label="Late Fine / Penalty (₹, optional)"
              type="number"
              step="0.01"
              placeholder="0.00"
              {...register('fine_amount')}
              error={errors.fine_amount?.message}
            />
            <p className="text-[11px] text-[var(--muted-ink)] mt-1">
              Any fine collected is credited directly to group fee income.
            </p>
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-[var(--border)]">
            <Button type="button" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Review Transaction
              <ArrowRight className="w-4 h-4 ml-1.5" />
            </Button>
          </div>
        </form>
      ) : (
        <div className="space-y-4">
          <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)] space-y-3">
            <div className="flex justify-between items-center text-xs pb-2 border-b border-[var(--border)]">
              <span className="text-[var(--muted-ink)]">Member</span>
              <span className="font-semibold text-[var(--ink)]">{memberName}</span>
            </div>

            <div className="flex justify-between items-center text-xs pb-2 border-b border-[var(--border)]">
              <span className="text-[var(--muted-ink)]">Period</span>
              <span className="font-mono text-[var(--ink)]">{currentValues.period}</span>
            </div>

            <div className="flex justify-between items-center text-xs pb-2 border-b border-[var(--border)]">
              <span className="text-[var(--muted-ink)]">Date</span>
              <span className="font-mono text-[var(--ink)]">{currentValues.collected_date}</span>
            </div>

            <div className="flex justify-between items-center text-xs pb-2 border-b border-[var(--border)]">
              <span className="text-[var(--muted-ink)]">Savings Deposit</span>
              <span className="font-mono font-medium text-[var(--ink)]">
                <MoneyText amount={currentValues.amount} />
              </span>
            </div>

            {Number(currentValues.fine_amount) > 0 && (
              <div className="flex justify-between items-center text-xs pb-2 border-b border-[var(--border)]">
                <span className="text-[var(--muted-ink)]">Late Fine</span>
                <span className="font-mono text-[var(--warning)]">
                  <MoneyText amount={currentValues.fine_amount} />
                </span>
              </div>
            )}

            <div className="flex justify-between items-center text-sm pt-1">
              <span className="font-bold text-[var(--ink)]">Total Cash Collected</span>
              <span className="font-mono font-bold text-[var(--primary)] text-base">
                <MoneyText
                  amount={(
                    Number(currentValues.amount || 0) + Number(currentValues.fine_amount || 0)
                  ).toFixed(2)}
                />
              </span>
            </div>
          </div>

          <div className="p-3 bg-[var(--surface-sunken)] rounded text-[11px] text-[var(--muted-ink)]">
            Notice: This posts a permanent, balanced journal entry (debiting Cash in Hand and
            crediting Member Savings) with idempotency protection.
          </div>

          <div className="flex justify-between items-center pt-4 border-t border-[var(--border)]">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setStep('form')}
              disabled={isSubmitting}
            >
              <ArrowLeft className="w-4 h-4 mr-1.5" />
              Back
            </Button>

            <Button
              type="button"
              variant="primary"
              onClick={handleFinalSubmit}
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                'Posting to Ledger...'
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4 mr-1.5" />
                  Confirm & Post
                </>
              )}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
};
