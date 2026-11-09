import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Table } from '../../components/ui/Table';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { GroupSettingsTab } from './GroupSettingsTab';
import { MemberCreateModal } from '../members/MemberCreateModal';
import {
  Building2,
  Users,
  Settings,
  Calendar,
  Plus,
  RefreshCw,
  ArrowLeft,
} from 'lucide-react';

export const GroupDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'members' | 'settings' | 'meetings'>('members');
  const [memberSearch, setMemberSearch] = useState('');
  const [memberStatus, setMemberStatus] = useState('');
  const [isEnrollOpen, setIsEnrollOpen] = useState(false);

  const canManageMembers = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';

  const {
    data: group,
    isLoading: isGroupLoading,
    isError: isGroupError,
    error: groupError,
    refetch: refetchGroup,
  } = useQuery({
    queryKey: ['group', id],
    queryFn: () => api.groups.get(id!),
    enabled: !!id,
  });

  const {
    data: membersData,
    isLoading: isMembersLoading,
    refetch: refetchMembers,
  } = useQuery({
    queryKey: ['group-members', id, memberSearch, memberStatus],
    queryFn: () =>
      api.members.listByGroup(id!, {
        query: memberSearch || undefined,
        status: memberStatus || undefined,
      }),
    enabled: !!id && activeTab === 'members',
  });

  if (isGroupLoading) {
    return (
      <div className="space-y-4 max-w-5xl mx-auto">
        <Skeleton height="2rem" width="30%" />
        <Skeleton height="6rem" width="100%" />
        <Skeleton height="16rem" width="100%" />
      </div>
    );
  }

  if (isGroupError || !group) {
    const is404 =
      groupError instanceof ApiException && groupError.status === 404;

    return (
      <div className="max-w-2xl mx-auto py-12">
        <EmptyState
          title={is404 ? 'Group Not Found' : 'Error Loading Group'}
          description={
            is404
              ? 'This self-help group either does not exist or you do not have permission to view it.'
              : groupError instanceof ApiException
              ? groupError.message
              : 'An unexpected error occurred.'
          }
          action={
            <Button variant="secondary" onClick={() => navigate('/groups')}>
              <ArrowLeft className="w-4 h-4 mr-1.5" />
              Back to Groups
            </Button>
          }
        />
      </div>
    );
  }

  const members = membersData?.items || [];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Back link */}
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/groups')}
          className="text-[var(--muted-ink)] hover:text-[var(--ink)] pl-0"
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" />
          All Groups
        </Button>
      </div>

      {/* Group Header Card */}
      <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)] shadow-sm">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded bg-[var(--accent-subtle)] border border-[var(--border)] text-[var(--primary)] flex items-center justify-center shrink-0">
              <Building2 className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
                  {group.name}
                </h1>
                <StatusChip
                  variant={
                    group.status === 'ACTIVE'
                      ? 'success'
                      : group.status === 'DORMANT'
                      ? 'warning'
                      : 'neutral'
                  }
                >
                  {group.status}
                </StatusChip>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--muted-ink)] mt-2 font-mono">
                <span>ID: {group.id.slice(0, 8)}</span>
                <span>•</span>
                <span>Schedule: {group.meeting_frequency}</span>
                <span>•</span>
                <span>Formed: {group.formation_date}</span>
                {group.village && (
                  <>
                    <span>•</span>
                    <span>{group.village}, {group.district}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                refetchGroup();
                if (activeTab === 'members') refetchMembers();
              }}
              title="Refresh data"
            >
              <RefreshCw className="w-4 h-4 text-[var(--muted-ink)]" />
            </Button>
          </div>
        </div>

        {/* Tab navigation */}
        <div className="flex items-center gap-2 mt-6 pt-4 border-t border-[var(--border)]">
          <button
            type="button"
            onClick={() => setActiveTab('members')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              activeTab === 'members'
                ? 'bg-[var(--accent-subtle)] text-[var(--primary)] font-semibold'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            Members ({members.length})
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('settings')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              activeTab === 'settings'
                ? 'bg-[var(--accent-subtle)] text-[var(--primary)] font-semibold'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
          >
            <Settings className="w-3.5 h-3.5" />
            Operational Rules & Settings
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('meetings')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              activeTab === 'meetings'
                ? 'bg-[var(--accent-subtle)] text-[var(--primary)] font-semibold'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            Meeting History
          </button>
        </div>
      </div>

      {/* Tab Body */}
      {activeTab === 'members' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 max-w-md w-full">
              <Input
                placeholder="Search member name..."
                value={memberSearch}
                onChange={(e) => setMemberSearch(e.target.value)}
                className="text-xs"
              />
              <div className="w-36 shrink-0">
                <Select
                  options={[
                    { value: '', label: 'All Status' },
                    { value: 'ACTIVE', label: 'Active' },
                    { value: 'EXITED', label: 'Exited' },
                    { value: 'SUSPENDED', label: 'Suspended' },
                  ]}
                  value={memberStatus}
                  onChange={(e) => setMemberStatus(e.target.value)}
                />
              </div>
            </div>

            {canManageMembers && (
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

          {isMembersLoading ? (
            <div className="space-y-2">
              <Skeleton height="3rem" />
              <Skeleton height="3rem" />
              <Skeleton height="3rem" />
            </div>
          ) : members.length === 0 ? (
            <div className="bg-[var(--surface)] p-8 rounded border border-[var(--border)]">
              <EmptyState
                title="No members found"
                description={
                  memberSearch || memberStatus
                    ? 'No members match the current search or status filter.'
                    : 'There are no enrolled members in this group yet.'
                }
                action={
                  canManageMembers ? (
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
                    <Table.Head>Name</Table.Head>
                    <Table.Head>Role</Table.Head>
                    <Table.Head>Contact</Table.Head>
                    <Table.Head>ID Proof</Table.Head>
                    <Table.Head>Joined Date</Table.Head>
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
                        {m.full_name}
                      </Table.Cell>
                      <Table.Cell className="text-xs">
                        <span className="font-mono text-[var(--primary)] font-semibold">
                          {m.roles?.join(', ') || 'MEMBER'}
                        </span>
                      </Table.Cell>
                      <Table.Cell className="text-xs text-[var(--muted-ink)] font-mono">
                        {m.phone || '—'}
                      </Table.Cell>
                      <Table.Cell className="text-xs text-[var(--muted-ink)] font-mono">
                        {m.id_proof_type && m.id_proof_last4
                          ? `${m.id_proof_type} (••${m.id_proof_last4})`
                          : '—'}
                      </Table.Cell>
                      <Table.Cell className="text-xs font-mono text-[var(--muted-ink)]">
                        {m.joined_on}
                      </Table.Cell>
                      <Table.Cell>
                        <StatusChip
                          variant={
                            m.status === 'ACTIVE'
                              ? 'success'
                              : m.status === 'EXITED'
                              ? 'neutral'
                              : 'warning'
                          }
                        >
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
        </div>
      )}

      {activeTab === 'settings' && (
        <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)]">
          <GroupSettingsTab groupId={id!} />
        </div>
      )}

      {activeTab === 'meetings' && (
        <div className="bg-[var(--surface)] p-12 rounded border border-[var(--border)] text-center">
          <Calendar className="w-10 h-10 text-[var(--muted-ink)] mx-auto mb-3" />
          <h3 className="font-serif text-lg font-bold text-[var(--ink)]">
            Meeting History & Attendance
          </h3>
          <p className="text-xs text-[var(--muted-ink)] max-w-md mx-auto mt-1">
            Meeting schedules, member attendance registers, minute-taking, and collection books
            will be activated in Phase 2.
          </p>
        </div>
      )}

      {/* Member Enrollment Modal */}
      {canManageMembers && (
        <MemberCreateModal
          groupId={id!}
          isOpen={isEnrollOpen}
          onClose={() => setIsEnrollOpen(false)}
          onSuccess={() => refetchMembers()}
        />
      )}
    </div>
  );
};
