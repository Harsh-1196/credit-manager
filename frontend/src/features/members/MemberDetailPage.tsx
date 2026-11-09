import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import { useAuth } from '../../lib/auth/AuthContext';
import { Button } from '../../components/ui/Button';
import { StatusChip } from '../../components/ui/StatusChip';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { MemberExitModal } from './MemberExitModal';
import {
  User,
  ArrowLeft,
  Building2,
  CreditCard,
  BookOpen,
  LogOut,
} from 'lucide-react';

export const MemberDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<'overview' | 'passbook' | 'loans'>('overview');
  const [isExitModalOpen, setIsExitModalOpen] = useState(false);

  const canManage = user?.role === 'ADMIN' || user?.role === 'GROUP_LEADER';

  const {
    data: member,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['member', id],
    queryFn: () => api.members.get(id!),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-4xl mx-auto">
        <Skeleton height="2rem" width="25%" />
        <Skeleton height="8rem" width="100%" />
        <Skeleton height="16rem" width="100%" />
      </div>
    );
  }

  if (isError || !member) {
    const is404 = error instanceof ApiException && error.status === 404;

    return (
      <div className="max-w-2xl mx-auto py-12">
        <EmptyState
          title={is404 ? 'Member Not Found' : 'Error Loading Profile'}
          description={
            is404
              ? 'This member either does not exist or belongs to a self-help group outside your permitted scope.'
              : error instanceof ApiException
              ? error.message
              : 'Failed to retrieve member profile.'
          }
          action={
            <Button variant="secondary" onClick={() => navigate('/members')}>
              <ArrowLeft className="w-4 h-4 mr-1.5" />
              Back to Members
            </Button>
          }
        />
      </div>
    );
  }

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
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Back button */}
      <div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/members')}
          className="text-[var(--muted-ink)] hover:text-[var(--ink)] pl-0"
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" />
          Members Directory
        </Button>
      </div>

      {/* Profile Header */}
      <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)] shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 rounded bg-[var(--surface-muted)] border border-[var(--border)] text-[var(--primary)] flex items-center justify-center shrink-0">
              <User className="w-8 h-8" />
            </div>

            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="font-serif text-2xl font-bold text-[var(--ink)]">
                  {member.full_name}
                </h1>
                <span className="px-2 py-0.5 rounded text-xs font-mono font-semibold bg-[var(--accent-subtle)] text-[var(--primary)] border border-[var(--border)]">
                  {member.roles?.join(', ') || 'MEMBER'}
                </span>
                <StatusChip variant={getStatusVariant(member.status) as any}>
                  {member.status}
                </StatusChip>
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--muted-ink)] mt-2 font-mono">
                <Link
                  to={`/groups/${member.shg_id}`}
                  className="flex items-center gap-1 hover:text-[var(--primary)] text-[var(--ink)]"
                >
                  <Building2 className="w-3.5 h-3.5" />
                  <span>View SHG</span>
                </Link>
                <span>•</span>
                <span>Enrolled: {member.joined_on}</span>
                {member.exited_on && (
                  <>
                    <span>•</span>
                    <span className="text-[var(--danger)]">
                      Exited: {member.exited_on}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {canManage && member.status === 'ACTIVE' && (
            <div>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setIsExitModalOpen(true)}
              >
                <LogOut className="w-4 h-4 mr-1.5" />
                Record Exit
              </Button>
            </div>
          )}
        </div>

        {/* Tab navigation */}
        <div className="flex items-center gap-2 mt-6 pt-4 border-t border-[var(--border)]">
          <button
            type="button"
            onClick={() => setActiveTab('overview')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              activeTab === 'overview'
                ? 'bg-[var(--accent-subtle)] text-[var(--primary)] font-semibold'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
          >
            <User className="w-3.5 h-3.5" />
            Profile Overview
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('passbook')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              activeTab === 'passbook'
                ? 'bg-[var(--accent-subtle)] text-[var(--primary)] font-semibold'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            Passbook & Savings
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('loans')}
            className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
              activeTab === 'loans'
                ? 'bg-[var(--accent-subtle)] text-[var(--primary)] font-semibold'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
          >
            <CreditCard className="w-3.5 h-3.5" />
            Credit & Loan Register
          </button>
        </div>
      </div>

      {/* Tab 1: Overview */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Personal Information */}
          <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)]">
            <h2 className="font-serif text-base font-bold text-[var(--ink)] mb-4">
              Personal Information
            </h2>

            <dl className="space-y-3 text-xs">
              <div>
                <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                  Full Legal Name
                </dt>
                <dd className="font-medium text-[var(--ink)] mt-0.5 text-sm">
                  {member.full_name}
                </dd>
              </div>

              <div>
                <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                  Phone Contact
                </dt>
                <dd className="font-mono text-[var(--ink)] mt-0.5">
                  {member.phone || 'Not provided'}
                </dd>
              </div>

              <div>
                <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                  Residential Address
                </dt>
                <dd className="text-[var(--ink)] mt-0.5">
                  {member.address || 'Not recorded'}
                </dd>
              </div>

              <div>
                <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                  Identity Proof
                </dt>
                <dd className="font-mono text-[var(--ink)] mt-0.5">
                  {member.id_proof_type && member.id_proof_last4
                    ? `${member.id_proof_type} (Ending with ${member.id_proof_last4})`
                    : 'None submitted'}
                </dd>
              </div>

              <div>
                <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                  Date of Birth
                </dt>
                <dd className="font-mono text-[var(--ink)] mt-0.5">
                  {member.date_of_birth || 'Not specified'}
                </dd>
              </div>
            </dl>
          </div>

          {/* SHG Affiliation & Audit Details */}
          <div className="bg-[var(--surface)] p-6 rounded border border-[var(--border)] flex flex-col justify-between">
            <div>
              <h2 className="font-serif text-base font-bold text-[var(--ink)] mb-4">
                SHG Affiliation & Status
              </h2>

              <dl className="space-y-3 text-xs">
                <div>
                  <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                    SHG Identifier
                  </dt>
                  <dd className="font-mono text-[var(--ink)] mt-0.5">
                    {member.shg_id}
                  </dd>
                </div>

                <div>
                  <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                    Designation / Role
                  </dt>
                  <dd className="font-medium text-[var(--ink)] mt-0.5">
                    {member.roles?.join(', ') || 'MEMBER'}
                  </dd>
                </div>

                <div>
                  <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                    Date of Enrollment
                  </dt>
                  <dd className="font-mono text-[var(--ink)] mt-0.5">
                    {member.joined_on}
                  </dd>
                </div>

                <div>
                  <dt className="text-[var(--muted-ink)] uppercase tracking-wider font-mono text-[10px]">
                    Current Status
                  </dt>
                  <dd className="mt-0.5">
                    <StatusChip variant={getStatusVariant(member.status) as any}>
                      {member.status}
                    </StatusChip>
                  </dd>
                </div>

                {member.exited_on && (
                  <div>
                    <dt className="text-[var(--danger)] uppercase tracking-wider font-mono text-[10px]">
                      Exit Date
                    </dt>
                    <dd className="font-mono text-[var(--danger)] mt-0.5">
                      {member.exited_on}
                    </dd>
                  </div>
                )}
              </dl>
            </div>

            <div className="mt-6 pt-4 border-t border-[var(--border)] text-[11px] text-[var(--muted-ink)]">
              Privacy Notice: Sensitive PII (full ID proof, phone, address) is masked per
              role authorization policy.
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Passbook Placeholder */}
      {activeTab === 'passbook' && (
        <div className="bg-[var(--surface)] p-12 rounded border border-[var(--border)] text-center">
          <BookOpen className="w-10 h-10 text-[var(--muted-ink)] mx-auto mb-3" />
          <h3 className="font-serif text-lg font-bold text-[var(--ink)]">
            Member Passbook & Savings Ledger
          </h3>
          <p className="text-xs text-[var(--muted-ink)] max-w-md mx-auto mt-1">
            Mandatory monthly savings deposits, voluntary savings balances, and passbook entries
            will be activated in Phase 2.
          </p>
        </div>
      )}

      {/* Tab 3: Loans Placeholder */}
      {activeTab === 'loans' && (
        <div className="bg-[var(--surface)] p-12 rounded border border-[var(--border)] text-center">
          <CreditCard className="w-10 h-10 text-[var(--muted-ink)] mx-auto mb-3" />
          <h3 className="font-serif text-lg font-bold text-[var(--ink)]">
            Credit & Loan Register
          </h3>
          <p className="text-xs text-[var(--muted-ink)] max-w-md mx-auto mt-1">
            Internal loan applications, repayment schedules, interest accruals, and default flags
            will be activated in Phase 3.
          </p>
        </div>
      )}

      {/* Exit Modal */}
      <MemberExitModal
        memberId={member.id}
        memberName={member.full_name}
        isOpen={isExitModalOpen}
        onClose={() => setIsExitModalOpen(false)}
        onSuccess={() => refetch()}
      />
    </div>
  );
};
