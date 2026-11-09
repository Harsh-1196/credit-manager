import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { api, ApiException } from '../../lib/api/client';
import type { GroupResponse } from '../../lib/api/types';

const groupCreateSchema = z.object({
  name: z.string().min(2, 'Group name must be at least 2 characters'),
  village: z.string().min(2, 'Village is required'),
  district: z.string().min(2, 'District is required'),
  ward: z.string().optional(),
  formation_date: z.string().min(1, 'Formation date is required'),
  meeting_day: z.string().min(1, 'Meeting day is required'),
  meeting_frequency: z.enum(['WEEKLY', 'BIWEEKLY', 'MONTHLY']),
  bank_account_label: z.string().optional(),
});

type GroupCreateFormData = z.infer<typeof groupCreateSchema>;

interface GroupCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (newGroup: GroupResponse) => void;
}

export const GroupCreateModal: React.FC<GroupCreateModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<GroupCreateFormData>({
    resolver: zodResolver(groupCreateSchema),
    defaultValues: {
      name: '',
      village: '',
      district: '',
      ward: '',
      formation_date: new Date().toISOString().split('T')[0],
      meeting_day: 'Monday',
      meeting_frequency: 'MONTHLY',
      bank_account_label: '',
    },
  });

  const onSubmit = async (data: GroupCreateFormData) => {
    setErrorMsg(null);
    try {
      const created = await api.groups.create({
        name: data.name,
        village: data.village,
        district: data.district,
        ward: data.ward || null,
        formation_date: data.formation_date,
        meeting_day: data.meeting_day,
        meeting_frequency: data.meeting_frequency,
        bank_account_label: data.bank_account_label || null,
      });
      reset();
      onSuccess(created);
      onClose();
    } catch (err) {
      if (err instanceof ApiException) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Failed to create group');
      }
    }
  };

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title="Create New Self-Help Group"
      description="Register a new SHG on the ledger platform"
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit(onSubmit)}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Creating...' : 'Register SHG'}
          </Button>
        </div>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {errorMsg && (
          <div className="p-3 text-xs bg-[var(--accent-subtle)] border border-[var(--danger)] text-[var(--danger)] rounded">
            {errorMsg}
          </div>
        )}

        <Input
          label="Group Name *"
          placeholder="e.g. Pragati Mahila SHG"
          error={errors.name?.message}
          {...register('name')}
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Village / Ward *"
            placeholder="e.g. Rampur"
            error={errors.village?.message}
            {...register('village')}
          />
          <Input
            label="District *"
            placeholder="e.g. Varanasi"
            error={errors.district?.message}
            {...register('district')}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Formation Date *"
            type="date"
            error={errors.formation_date?.message}
            {...register('formation_date')}
          />

          <Select
            label="Meeting Frequency *"
            error={errors.meeting_frequency?.message}
            {...register('meeting_frequency')}
            options={[
              { value: 'MONTHLY', label: 'Monthly' },
              { value: 'BIWEEKLY', label: 'Bi-Weekly' },
              { value: 'WEEKLY', label: 'Weekly' },
            ]}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Meeting Day *"
            placeholder="e.g. First Monday"
            error={errors.meeting_day?.message}
            {...register('meeting_day')}
          />
          <Input
            label="Bank Account Label"
            placeholder="e.g. SBI A/c ...3847"
            error={errors.bank_account_label?.message}
            {...register('bank_account_label')}
          />
        </div>
      </form>
    </Dialog>
  );
};
