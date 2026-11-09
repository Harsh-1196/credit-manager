import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { api, ApiException } from '../../lib/api/client';
import type { MemberResponse } from '../../lib/api/types';

const memberExitSchema = z.object({
  exited_on: z.string().min(1, 'Exit date is required'),
  reason: z.string().optional(),
});

type MemberExitFormData = z.infer<typeof memberExitSchema>;

interface MemberExitModalProps {
  memberId: string;
  memberName: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (updated: MemberResponse) => void;
}

export const MemberExitModal: React.FC<MemberExitModalProps> = ({
  memberId,
  memberName,
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
  } = useForm<MemberExitFormData>({
    resolver: zodResolver(memberExitSchema),
    defaultValues: {
      exited_on: new Date().toISOString().split('T')[0],
      reason: '',
    },
  });

  const onSubmit = async (data: MemberExitFormData) => {
    setErrorMsg(null);
    try {
      const updated = await api.members.exit(memberId, {
        exited_on: data.exited_on,
        reason: data.reason || null,
      });
      reset();
      onSuccess(updated);
      onClose();
    } catch (err) {
      if (err instanceof ApiException) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Failed to process member exit');
      }
    }
  };

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title="Record Member Exit"
      description={`Mark ${memberName} as exited from the SHG. Outstanding balances or settlement must be finalized.`}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={handleSubmit(onSubmit)}
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Processing...' : 'Confirm Exit'}
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
          label="Date of Exit *"
          type="date"
          error={errors.exited_on?.message}
          {...register('exited_on')}
        />

        <Input
          label="Reason for Exit"
          placeholder="e.g. Relocated to another district"
          error={errors.reason?.message}
          {...register('reason')}
        />
      </form>
    </Dialog>
  );
};
