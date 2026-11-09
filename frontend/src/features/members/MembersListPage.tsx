import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { Table } from '../../components/ui/Table';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { MemberCreateModal } from './MemberCreateModal';
import { Users, Plus, RefreshCw } from 'lucide-react';

export const MembersListPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);

  const canEnroll = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';

  // Fetch groups accessible to the user
  const { data: groupsData, isLoading: isGroupsLoading } = useQuery({
    queryKey: ['user-groups'],
    queryFn: () => api.groups.list(),
  });

  const groups = groupsData?.items || [];

  // Default to first group when groups are loaded
  useEffect(() => {
    if (groups.length > 0 && !selectedGroupId) {
      setSelectedGroupId(groups[0].id);
    }
  }, [groups, selectedGroupId]);

  // Fetch members for selected group
  const {
    data: membersData,
    isLoading: isMembersLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['members', selectedGroupId, searchQuery, statusFilter],
    queryFn: () =>
      api.members.listByGroup(selectedGroupId, {
        query: searchQuery || undefined,
        status: statusFilter || undefined,
      }),
    enabled: !!selectedGroupId,
  });

  const members = membersData?.items || [];

  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return 'success';
      case 'EXITED':
        return 'neutral';
      case 'SUSPENDED':
        return 'warning';
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
            SHG Member Directory
          </h1>
          <p className="text-sm text-[var(--muted-ink)] mt-0.5">
            Member profiles, roles, and status across self-help groups
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            title="Reload list"
          >
            <RefreshCw className="w-4 h-4 text-[var(--muted-ink)]" />
          </Button>

          {canEnroll && selectedGroupId && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsEnrollOpen(true)}
            >
              <Plus className="w-4 h-4 mr-1.5" />
              Enroll Member
            </Button>
          )}
        </div>
      </div>

      {/* Group & Filter Controls */}
      <div className="bg-[var(--surface)] p-4 rounded border border-[var(--border)] flex flex-col md:flex-row items-stretch md:items-center gap-4">
        <div className="w-full md:w-64">
          <Select
            label="Selected Group"
            value={selectedGroupId}
            onChange={(e) => setSelectedGroupId(e.target.value)}
            disabled={isGroupsLoading || groups.length === 0}
            options={
              groups.length > 0
                ? groups.map((g) => ({
                    value: g.id,
                    label: `${g.name} (${g.village || g.district})`,
                  }))
                : [{ value: '', label: 'No groups assigned' }]
            }
          />
        </div>

        <div className="flex-1 flex flex-col sm:flex-row items-center gap-3 pt-0 md:pt-5">
          <div className="w-full sm:flex-1">
            <Input
              placeholder="Search by member name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="w-full sm:w-44">
            <Select
              options={[
                { value: '', label: 'All Statuses' },
                { value: 'ACTIVE', label: 'Active' },
                { value: 'EXITED', label: 'Exited' },
                { value: 'SUSPENDED', label: 'Suspended' },
              ]}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Content Area */}
      {isGroupsLoading || (selectedGroupId && isMembersLoading) ? (
        <div className="space-y-2">
          <Skeleton height="3rem" />
          <Skeleton height="3rem" />
          <Skeleton height="3rem" />
        </div>
      ) : groups.length === 0 ? (
        <div className="p-8 bg-[var(--surface)] rounded border border-[var(--border)]">
          <EmptyState
            title="No groups assigned"
            description="You do not have access to any self-help groups."
          />
        </div>
      ) : isError ? (
        <div className="p-8 bg-[var(--surface)] rounded border border-[var(--border)]">
          <EmptyState
            title="Failed to load members"
            description={
              error instanceof ApiException
                ? error.message
                : 'Could not fetch member records.'
            }
            action={
              <Button variant="secondary" onClick={() => refetch()}>
                Retry
              </Button>
            }
          />
        </div>
      ) : members.length === 0 ? (
        <div className="p-8 bg-[var(--surface)] rounded border border-[var(--border)]">
          <EmptyState
            title="No members enrolled"
            description={
              searchQuery || statusFilter
                ? 'No members match the active filters.'
                : 'This group does not have any enrolled members yet.'
            }
            action={
              canEnroll && selectedGroupId ? (
                <Button variant="primary" onClick={() => setIsEnrollOpen(true)}>
                  <Plus className="w-4 h-4 mr-1.5" />
                  Enroll First Member
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
                <Table.Head>Member Name</Table.Head>
                <Table.Head>Role</Table.Head>
                <Table.Head>Contact</Table.Head>
                <Table.Head>ID Proof</Table.Head>
                <Table.Head>Date Joined</Table.Head>
                <Table.Head>Status</Table.Head>
                <Table.Head className="text-right">Action</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {members.map((m) => (
                <Table.Row
                  key={m.id}
                  className="cursor-pointer hover:bg-[var(--surface-muted)] transition-colors"
                  onClick={() => navigate(`/members/${m.id}`)}
                >
                  <Table.Cell className="font-medium text-[var(--ink)]">
                    <div className="flex items-center gap-2">
                      <Users className="w-4 h-4 text-[var(--primary)] shrink-0" />
                      <span>{m.full_name}</span>
                    </div>
                  </Table.Cell>
                  <Table.Cell className="text-xs">
                    <span className="font-mono text-[var(--primary)] font-semibold">
                      {m.roles?.join(', ') || 'MEMBER'}
                    </span>
                  </Table.Cell>
                  <Table.Cell className="text-xs font-mono text-[var(--muted-ink)]">
                    {m.phone || '—'}
                  </Table.Cell>
                  <Table.Cell className="text-xs font-mono text-[var(--muted-ink)]">
                    {m.id_proof_type && m.id_proof_last4
                      ? `${m.id_proof_type} (••${m.id_proof_last4})`
                      : '—'}
                  </Table.Cell>
                  <Table.Cell className="text-xs font-mono text-[var(--muted-ink)]">
                    {m.joined_on}
                  </Table.Cell>
                  <Table.Cell>
                    <StatusChip variant={getStatusVariant(m.status) as any}>
                      {m.status}
                    </StatusChip>
                  </Table.Cell>
                  <Table.Cell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/members/${m.id}`);
                      }}
                    >
                      Profile
                    </Button>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </div>
      )}

      {/* Member Enrollment Modal */}
      {canEnroll && selectedGroupId && (
        <MemberCreateModal
          groupId={selectedGroupId}
          isOpen={isEnrollOpen}
          onClose={() => setIsEnrollOpen(false)}
          onSuccess={() => refetch()}
        />
      )}
    </div>
  );
};
