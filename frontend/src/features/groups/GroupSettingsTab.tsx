import React, { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import type { InterestType } from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { Check } from 'lucide-react';

const groupSettingsSchema = z.object({
  monthly_saving_amount: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Must be a valid amount (e.g. 200.00)'),
  default_interest_rate: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Must be a valid percentage (e.g. 2.00)'),
  interest_type: z.enum(['FLAT', 'REDUCING']),
  late_fine_per_day: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Must be a valid amount (e.g. 5.00)'),
  fine_grace_days: z.coerce.number().int().min(0).max(30),
  max_loan_multiple: z.string().regex(/^\d+(\.\d{1,2})?$/, 'Must be a valid number (e.g. 3.00)'),
  min_tenure_months: z.coerce.number().int().min(1).max(60),
  max_tenure_months: z.coerce.number().int().min(1).max(120),
});

type GroupSettingsFormData = z.infer<typeof groupSettingsSchema>;

interface GroupSettingsTabProps {
  groupId: string;
}

export const GroupSettingsTab: React.FC<GroupSettingsTabProps> = ({ groupId }) => {
  const { user } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const canEdit = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting, isDirty },
  } = useForm<GroupSettingsFormData>({
    resolver: zodResolver(groupSettingsSchema),
  });

  useEffect(() => {
    let isMounted = true;
    const fetchSettings = async () => {
      try {
        setIsLoading(true);
        const settings = await api.groups.getSettings(groupId);
        if (isMounted) {
          reset({
            monthly_saving_amount: settings.monthly_saving_amount,
            default_interest_rate: settings.default_interest_rate,
            interest_type: settings.interest_type,
            late_fine_per_day: settings.late_fine_per_day,
            fine_grace_days: settings.fine_grace_days,
            max_loan_multiple: settings.max_loan_multiple,
            min_tenure_months: settings.min_tenure_months,
            max_tenure_months: settings.max_tenure_months,
          });
        }
      } catch (err) {
        if (isMounted) {
          setErrorMsg(err instanceof ApiException ? err.message : 'Failed to load settings');
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchSettings();
    return () => {
      isMounted = false;
    };
  }, [groupId, reset]);

  const onSubmit = async (data: GroupSettingsFormData) => {
    setErrorMsg(null);
    setSaveSuccess(false);
    try {
      const updated = await api.groups.updateSettings(groupId, {
        monthly_saving_amount: data.monthly_saving_amount,
        default_interest_rate: data.default_interest_rate,
        interest_type: data.interest_type as InterestType,
        late_fine_per_day: data.late_fine_per_day,
        fine_grace_days: data.fine_grace_days,
        max_loan_multiple: data.max_loan_multiple,
        min_tenure_months: data.min_tenure_months,
        max_tenure_months: data.max_tenure_months,
      });
      reset({
        monthly_saving_amount: updated.monthly_saving_amount,
        default_interest_rate: updated.default_interest_rate,
        interest_type: updated.interest_type,
        late_fine_per_day: updated.late_fine_per_day,
        fine_grace_days: updated.fine_grace_days,
        max_loan_multiple: updated.max_loan_multiple,
        min_tenure_months: updated.min_tenure_months,
        max_tenure_months: updated.max_tenure_months,
      });
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 4000);
    } catch (err) {
      if (err instanceof ApiException) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Failed to update group settings');
      }
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-2xl">
        <Skeleton height="3rem" />
        <Skeleton height="3rem" />
        <Skeleton height="3rem" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h2 className="font-serif text-lg font-bold text-[var(--ink)]">
          Group Operational Rules
        </h2>
        <p className="text-xs text-[var(--muted-ink)] mt-0.5">
          Savings commitments, loan policies, interest calculation types, and penalties.
        </p>
      </div>

      {saveSuccess && (
        <div className="mb-4 p-3 text-xs bg-[var(--accent-subtle)] border border-[var(--primary)] text-[var(--primary)] rounded flex items-center gap-2 font-medium">
          <Check className="w-4 h-4 shrink-0" />
          <span>Group settings updated and recorded to the audit log.</span>
        </div>
      )}

      {errorMsg && (
        <div className="mb-4 p-3 text-xs bg-[var(--accent-subtle)] border border-[var(--danger)] text-[var(--danger)] rounded">
          {errorMsg}
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Mandatory Monthly Savings (₹)"
            disabled={!canEdit}
            error={errors.monthly_saving_amount?.message}
            helperText="Collected per member per meeting"
            {...register('monthly_saving_amount')}
          />

          <Input
            label="Default Monthly Interest Rate (%)"
            disabled={!canEdit}
            error={errors.default_interest_rate?.message}
            helperText="Applied to internal loans"
            {...register('default_interest_rate')}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Select
            label="Interest Calculation Method"
            disabled={!canEdit}
            error={errors.interest_type?.message}
            options={[
              { value: 'REDUCING', label: 'Reducing Balance' },
              { value: 'FLAT', label: 'Flat Interest' },
            ]}
            {...register('interest_type')}
          />

          <Input
            label="Max Loan Multiple (x Savings)"
            disabled={!canEdit}
            error={errors.max_loan_multiple?.message}
            helperText="Maximum borrowing as multiple of savings"
            {...register('max_loan_multiple')}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Input
            label="Min Tenure (Months)"
            type="number"
            disabled={!canEdit}
            error={errors.min_tenure_months?.message}
            {...register('min_tenure_months')}
          />

          <Input
            label="Max Tenure (Months)"
            type="number"
            disabled={!canEdit}
            error={errors.max_tenure_months?.message}
            {...register('max_tenure_months')}
          />

          <Input
            label="Late Fine / Day (₹)"
            disabled={!canEdit}
            error={errors.late_fine_per_day?.message}
            {...register('late_fine_per_day')}
          />
        </div>

        {canEdit && (
          <div className="pt-4 flex items-center justify-end gap-3 border-t border-[var(--border)]">
            <Button
              type="submit"
              variant="primary"
              disabled={isSubmitting || !isDirty}
            >
              {isSubmitting ? 'Saving...' : 'Save Settings'}
            </Button>
          </div>
        )}
      </form>
    </div>
  );
};
