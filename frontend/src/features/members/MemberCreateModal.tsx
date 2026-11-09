import React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { api, ApiException } from '../../lib/api/client';
import type { MemberResponse, OfficeBearerRole } from '../../lib/api/types';

const memberCreateSchema = z.object({
  full_name: z.string().min(2, 'Full name is required (min 2 characters)'),
  phone: z
    .string()
    .regex(/^[6-9]\d{9}$/, 'Must be a valid 10-digit Indian mobile number')
    .or(z.literal('')),
  address: z.string().optional(),
  id_proof_type: z.enum(['AADHAAR', 'VOTER_ID', 'PAN', 'RATION_CARD', '']).optional(),
  id_proof_number: z.string().optional(),
  date_of_birth: z.string().optional(),
  joined_on: z.string().min(1, 'Joining date is required'),
  role: z.enum(['PRESIDENT', 'SECRETARY', 'TREASURER', 'MEMBER']),
});

type MemberCreateFormData = z.infer<typeof memberCreateSchema>;

interface MemberCreateModalProps {
  groupId: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (newMember: MemberResponse) => void;
}

export const MemberCreateModal: React.FC<MemberCreateModalProps> = ({
  groupId,
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
  } = useForm<MemberCreateFormData>({
    resolver: zodResolver(memberCreateSchema),
    defaultValues: {
      full_name: '',
      phone: '',
      address: '',
      id_proof_type: 'AADHAAR',
      id_proof_number: '',
      date_of_birth: '',
      joined_on: new Date().toISOString().split('T')[0],
      role: 'MEMBER',
    },
  });

  const onSubmit = async (data: MemberCreateFormData) => {
    setErrorMsg(null);
    try {
      const created = await api.members.create(groupId, {
        full_name: data.full_name,
        phone: data.phone || null,
        address: data.address || null,
        id_proof_type: data.id_proof_type || null,
        id_proof_number: data.id_proof_number || null,
        date_of_birth: data.date_of_birth || null,
        joined_on: data.joined_on,
        role: data.role as OfficeBearerRole,
      });
      reset();
      onSuccess(created);
      onClose();
    } catch (err) {
      if (err instanceof ApiException) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Failed to add member to SHG');
      }
    }
  };

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title="Enroll New SHG Member"
      description="Add a member to the self-help group roster. ID proof will only store the last 4 digits for privacy."
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
            {isSubmitting ? 'Enrolling...' : 'Enroll Member'}
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
          label="Full Name *"
          placeholder="e.g. Radhika Devi"
          error={errors.full_name?.message}
          {...register('full_name')}
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Mobile Phone"
            type="tel"
            placeholder="10 digits (e.g. 9876543210)"
            error={errors.phone?.message}
            {...register('phone')}
          />
          <Select
            label="Leadership Role *"
            error={errors.role?.message}
            {...register('role')}
            options={[
              { value: 'MEMBER', label: 'General Member' },
              { value: 'PRESIDENT', label: 'President' },
              { value: 'SECRETARY', label: 'Secretary' },
              { value: 'TREASURER', label: 'Treasurer' },
            ]}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Date of Joining *"
            type="date"
            error={errors.joined_on?.message}
            {...register('joined_on')}
          />
          <Input
            label="Date of Birth"
            type="date"
            error={errors.date_of_birth?.message}
            {...register('date_of_birth')}
          />
        </div>

        <Input
          label="Residential Address"
          placeholder="House no., street, hamlet"
          error={errors.address?.message}
          {...register('address')}
        />

        <div className="grid grid-cols-2 gap-3">
          <Select
            label="ID Proof Type"
            error={errors.id_proof_type?.message}
            {...register('id_proof_type')}
            options={[
              { value: '', label: 'None / Pending' },
              { value: 'AADHAAR', label: 'Aadhaar Card' },
              { value: 'VOTER_ID', label: 'Voter ID' },
              { value: 'PAN', label: 'PAN Card' },
              { value: 'RATION_CARD', label: 'Ration Card' },
            ]}
          />
          <Input
            label="ID Proof Number"
            placeholder="Full number or last 4 digits"
            helperText="Stored as last 4 digits only (SPEC Section 9)"
            error={errors.id_proof_number?.message}
            {...register('id_proof_number')}
          />
        </div>
      </form>
    </Dialog>
  );
};
