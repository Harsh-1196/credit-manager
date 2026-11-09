import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { Table } from '../../components/ui/Table';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Select } from '../../components/ui/Select';
import { GroupCreateModal } from './GroupCreateModal';
import { Plus, Building2, RefreshCw } from 'lucide-react';

export const GroupsListPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['groups', statusFilter],
    queryFn: () => api.groups.list({ status: statusFilter || undefined }),
  });

  const groups = data?.items || [];
  const isAdmin = user?.role === 'ADMIN';

  const formatMeetingFreq = (freq: string) => {
    switch (freq) {
      case 'WEEKLY':
        return 'Weekly';
      case 'BIWEEKLY':
        return 'Bi-Weekly';
      case 'MONTHLY':
        return 'Monthly';
      default:
        return freq;
    }
  };

  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return 'success';
      case 'DORMANT':
        return 'warning';
      case 'CLOSED':
        return 'neutral';
      default:
        return 'neutral';
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
            Self-Help Groups
          </h1>
          <p className="text-sm text-[var(--muted-ink)] mt-0.5">
            {isAdmin
              ? 'All registered SHG units in the network'
              : 'Groups assigned to your role'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            title="Reload list"
            aria-label="Reload list"
          >
            <RefreshCw className="w-4 h-4 text-[var(--muted-ink)]" />
          </Button>

          {isAdmin && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsCreateOpen(true)}
            >
              <Plus className="w-4 h-4 mr-1.5" />
              New SHG
            </Button>
          )}
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex items-center gap-4 bg-[var(--surface)] p-3 rounded border border-[var(--border)]">
        <div className="w-48">
          <Select
            options={[
              { value: '', label: 'All Statuses' },
              { value: 'ACTIVE', label: 'Active' },
              { value: 'DORMANT', label: 'Dormant' },
              { value: 'CLOSED', label: 'Closed' },
            ]}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          />
        </div>
        <div className="text-xs text-[var(--muted-ink)] font-mono">
          Showing {groups.length} group{groups.length === 1 ? '' : 's'}
        </div>
      </div>

      {/* State rendering: Loading, Error, Empty, or Table */}
      {isLoading ? (
        <div className="space-y-2">
          <Skeleton height="3rem" />
          <Skeleton height="3rem" />
          <Skeleton height="3rem" />
          <Skeleton height="3rem" />
        </div>
      ) : isError ? (
        <div className="p-6 bg-[var(--surface)] rounded border border-[var(--border)]">
          <EmptyState
            title="Failed to load groups"
            description={
              error instanceof ApiException
                ? error.message
                : 'An unexpected error occurred while fetching the group list.'
            }
            action={
              <Button variant="secondary" onClick={() => refetch()}>
                Retry
              </Button>
            }
          />
        </div>
      ) : groups.length === 0 ? (
        <div className="p-8 bg-[var(--surface)] rounded border border-[var(--border)]">
          <EmptyState
            title="No groups found"
            description={
              statusFilter
                ? 'No groups match the selected status filter.'
                : 'There are no active SHGs assigned to your account.'
            }
            action={
              isAdmin ? (
                <Button variant="primary" onClick={() => setIsCreateOpen(true)}>
                  <Plus className="w-4 h-4 mr-1.5" />
                  Create First SHG
                </Button>
              ) : undefined
            }
          />
        </div>
      ) : (
        <div className="bg-[var(--surface)] rounded border border-[var(--border)] overflow-hidden">
          <Table>
            <Table.Header>
              <Table.Row>
                <Table.Head>Group Name</Table.Head>
                <Table.Head>Code</Table.Head>
                <Table.Head>Meeting Schedule</Table.Head>
                <Table.Head>Location</Table.Head>
                <Table.Head>Formation Date</Table.Head>
                <Table.Head>Status</Table.Head>
                <Table.Head className="text-right">Action</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {groups.map((group) => (
                <Table.Row
                  key={group.id}
                  className="cursor-pointer hover:bg-[var(--surface-muted)] transition-colors"
                  onClick={() => navigate(`/groups/${group.id}`)}
                >
                  <Table.Cell className="font-medium text-[var(--ink)]">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-4 h-4 text-[var(--primary)] shrink-0" />
                      <span>{group.name}</span>
                    </div>
                  </Table.Cell>
                  <Table.Cell className="font-mono text-xs text-[var(--muted-ink)]">
                    {group.id.slice(0, 8)}
                  </Table.Cell>
                  <Table.Cell className="text-xs">
                    {formatMeetingFreq(group.meeting_frequency)}
                  </Table.Cell>
                  <Table.Cell className="text-xs text-[var(--muted-ink)]">
                    {[group.village, group.district].filter(Boolean).join(', ') || '—'}
                  </Table.Cell>
                  <Table.Cell className="font-mono text-xs text-[var(--muted-ink)]">
                    {group.formation_date}
                  </Table.Cell>
                  <Table.Cell>
                    <StatusChip variant={getStatusVariant(group.status) as any}>
                      {group.status}
                    </StatusChip>
                  </Table.Cell>
                  <Table.Cell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/groups/${group.id}`);
                      }}
                    >
                      View
                    </Button>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </div>
      )}

      {/* Create Modal */}
      {isAdmin && (
        <GroupCreateModal
          isOpen={isCreateOpen}
          onClose={() => setIsCreateOpen(false)}
          onSuccess={() => refetch()}
        />
      )}
    </div>
  );
};
