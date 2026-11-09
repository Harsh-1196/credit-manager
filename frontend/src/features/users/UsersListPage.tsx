import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, ApiException } from '../../lib/api/client';
import { Button } from '../../components/ui/Button';
import { Table } from '../../components/ui/Table';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Dialog } from '../../components/ui/Dialog';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import type { UserRole } from '../../lib/api/types';
import { UserCheck, Plus, RefreshCw, UserX } from 'lucide-react';

const userCreateSchema = z.object({
  email: z.string().email('Valid email is required'),
  phone: z.string().regex(/^[6-9]\d{9}$/, 'Must be a 10-digit mobile number').or(z.literal('')),
  password: z.string().min(8, 'Password must be at least 8 characters'),
  role: z.enum(['ADMIN', 'GROUP_LEADER', 'MEMBER', 'AUDITOR']),
});

type UserCreateFormData = z.infer<typeof userCreateSchema>;

export const UsersListPage: React.FC = () => {
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.users.list(),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<UserCreateFormData>({
    resolver: zodResolver(userCreateSchema),
    defaultValues: {
      email: '',
      phone: '',
      password: '',
      role: 'GROUP_LEADER',
    },
  });

  const users = data?.items || [];

  const handleCreate = async (formData: UserCreateFormData) => {
    setErrorMsg(null);
    try {
      await api.users.create({
        email: formData.email,
        phone: formData.phone || null,
        password: formData.password,
        role: formData.role as UserRole,
        group_ids: [],
      });
      reset();
      setIsCreateOpen(false);
      refetch();
    } catch (err) {
      if (err instanceof ApiException) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Failed to create user');
      }
    }
  };

  const handleDeactivate = async (id: string) => {
    if (window.confirm('Are you sure you want to deactivate this user account?')) {
      try {
        await api.users.deactivate(id);
        refetch();
      } catch (err) {
        alert(err instanceof ApiException ? err.message : 'Failed to deactivate user');
      }
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
            User Accounts & Roles
          </h1>
          <p className="text-sm text-[var(--muted-ink)] mt-0.5">
            Manage system access credentials and security roles (ADMIN only)
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => refetch()} title="Reload">
            <RefreshCw className="w-4 h-4 text-[var(--muted-ink)]" />
          </Button>

          <Button variant="primary" size="sm" onClick={() => setIsCreateOpen(true)}>
            <Plus className="w-4 h-4 mr-1.5" />
            Add User
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton height="3rem" />
          <Skeleton height="3rem" />
          <Skeleton height="3rem" />
        </div>
      ) : isError ? (
        <div className="p-8 bg-[var(--surface)] rounded border border-[var(--border)]">
          <EmptyState
            title="Failed to load users"
            description={error instanceof ApiException ? error.message : 'Error fetching user directory.'}
            action={
              <Button variant="secondary" onClick={() => refetch()}>
                Retry
              </Button>
            }
          />
        </div>
      ) : (
        <div className="bg-[var(--surface)] rounded border border-[var(--border)] overflow-hidden">
          <Table>
            <Table.Header>
              <Table.Row>
                <Table.Head>Email</Table.Head>
                <Table.Head>Role</Table.Head>
                <Table.Head>Phone</Table.Head>
                <Table.Head>Status</Table.Head>
                <Table.Head>User ID</Table.Head>
                <Table.Head className="text-right">Action</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {users.map((u) => (
                <Table.Row key={u.id}>
                  <Table.Cell className="font-medium text-[var(--ink)]">
                    <div className="flex items-center gap-2">
                      <UserCheck className="w-4 h-4 text-[var(--primary)] shrink-0" />
                      <span>{u.email}</span>
                    </div>
                  </Table.Cell>
                  <Table.Cell>
                    <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--primary)]">
                      {u.role}
                    </span>
                  </Table.Cell>
                  <Table.Cell className="font-mono text-xs text-[var(--muted-ink)]">
                    {u.phone || '—'}
                  </Table.Cell>
                  <Table.Cell>
                    <StatusChip variant={u.is_active ? 'success' : 'neutral'}>
                      {u.is_active ? 'ACTIVE' : 'INACTIVE'}
                    </StatusChip>
                  </Table.Cell>
                  <Table.Cell className="font-mono text-xs text-[var(--muted-ink)]">
                    {u.id.slice(0, 8)}
                  </Table.Cell>
                  <Table.Cell className="text-right">
                    {u.is_active && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeactivate(u.id)}
                        className="text-[var(--danger)] hover:bg-[var(--surface-muted)]"
                      >
                        <UserX className="w-3.5 h-3.5 mr-1" />
                        Deactivate
                      </Button>
                    )}
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </div>
      )}

      {/* Create User Dialog */}
      <Dialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Create User Account"
        description="Provision credentials for a group leader, auditor, or member"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSubmit(handleCreate)} disabled={isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create Account'}
            </Button>
          </div>
        }
      >
        <form onSubmit={handleSubmit(handleCreate)} className="space-y-4">
          {errorMsg && (
            <div className="p-3 text-xs bg-[var(--accent-subtle)] border border-[var(--danger)] text-[var(--danger)] rounded">
              {errorMsg}
            </div>
          )}

          <Input
            label="Email Address *"
            type="email"
            placeholder="e.g. newleader@shg.org"
            error={errors.email?.message}
            {...register('email')}
          />

          <Input
            label="Phone Number"
            type="tel"
            placeholder="10 digits (e.g. 9876543210)"
            error={errors.phone?.message}
            {...register('phone')}
          />

          <Input
            label="Temporary Password *"
            type="password"
            placeholder="Minimum 8 characters"
            error={errors.password?.message}
            {...register('password')}
          />

          <Select
            label="System Role *"
            error={errors.role?.message}
            options={[
              { value: 'GROUP_LEADER', label: 'Group Leader' },
              { value: 'AUDITOR', label: 'Auditor' },
              { value: 'MEMBER', label: 'Member' },
              { value: 'ADMIN', label: 'Administrator' },
            ]}
            {...register('role')}
          />
        </form>
      </Dialog>
    </div>
  );
};
