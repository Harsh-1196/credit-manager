import React, { useState, useEffect } from 'react';
import { useAuth } from '../../lib/auth/AuthContext';
import { apiClient } from '../../lib/api/client';
import type {
  GroupResponse,
  GroupSettingsResponse,
  GroupSettingsUpdateRequest,
  UserResponse,
  InterestType,
} from '../../lib/api/types';
import {
  Sliders,
  Users,
  Building2,
  CheckCircle2,
  AlertCircle,
  Save,
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const isLeaderOrAdmin = isAdmin || user?.role === 'GROUP_LEADER';

  const [activeTab, setActiveTab] = useState<'rules' | 'users'>('rules');

  // Groups & Settings
  const [groups, setGroups] = useState<GroupResponse[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [settings, setSettings] = useState<GroupSettingsResponse | null>(null);

  // Form State
  const [monthlySaving, setMonthlySaving] = useState<string>('500');
  const [interestRate, setInterestRate] = useState<string>('12.0');
  const [interestType, setInterestType] = useState<InterestType>('REDUCING');
  const [lateFinePerDay, setLateFinePerDay] = useState<string>('5');
  const [fineGraceDays, setFineGraceDays] = useState<number>(5);
  const [maxTenorMonths, setMaxTenorMonths] = useState<number>(24);
  const [loanCeilingMultiplier, setLoanCeilingMultiplier] = useState<string>('3.0');

  const [savingSettings, setSavingSettings] = useState<boolean>(false);
  const [settingsSuccess, setSettingsSuccess] = useState<string | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);

  // Users Tab (for ADMIN)
  const [usersList, setUsersList] = useState<UserResponse[]>([]);
  const [userSearch, setUserSearch] = useState<string>('');
  const [usersLoading, setUsersLoading] = useState<boolean>(false);

  // 1. Fetch groups
  useEffect(() => {
    apiClient.groups
      .list()
      .then((res) => {
        setGroups(res.items);
        if (res.items.length > 0 && !selectedGroupId) {
          setSelectedGroupId(res.items[0].id);
        }
      })
      .catch((err) => setSettingsError(err.message || 'Failed to load groups'));
  }, []);

  // 2. Fetch group settings
  useEffect(() => {
    if (selectedGroupId) {
      setSettingsError(null);
      setSettingsSuccess(null);
      apiClient.groups
        .getSettings(selectedGroupId)
        .then((res) => {
          setSettings(res);
          setMonthlySaving(res.monthly_saving_amount);
          setInterestRate(res.default_interest_rate);
          setInterestType(res.interest_type);
          setLateFinePerDay(res.late_fine_per_day);
          setFineGraceDays(res.fine_grace_days);
          if (res.max_tenure_months) setMaxTenorMonths(res.max_tenure_months);
          if (res.max_loan_multiple) setLoanCeilingMultiplier(res.max_loan_multiple);
        })
        .catch((err) => setSettingsError(err.message || 'Failed to fetch group settings'));
    }
  }, [selectedGroupId]);

  // 3. Fetch users for admin
  useEffect(() => {
    if (isAdmin && activeTab === 'users') {
      setUsersLoading(true);
      apiClient.users
        .list()
        .then((res) => setUsersList(res.items))
        .catch(() => {})
        .finally(() => setUsersLoading(false));
    }
  }, [isAdmin, activeTab]);

  // 4. Save Settings Handler
  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedGroupId) return;

    setSavingSettings(true);
    setSettingsSuccess(null);
    setSettingsError(null);

    const updatePayload: GroupSettingsUpdateRequest = {
      monthly_saving_amount: monthlySaving,
      default_interest_rate: interestRate,
      interest_type: interestType,
      late_fine_per_day: lateFinePerDay,
      fine_grace_days: Number(fineGraceDays),
      max_tenure_months: Number(maxTenorMonths),
      max_loan_multiple: loanCeilingMultiplier,
    };

    try {
      const updated = await apiClient.groups.updateSettings(selectedGroupId, updatePayload);
      setSettings(updated);
      setSettingsSuccess('Group financial rules and lending parameters saved successfully.');
    } catch (err: any) {
      setSettingsError(err.message || 'Failed to update settings.');
    } finally {
      setSavingSettings(false);
    }
  };

  const filteredUsers = usersList.filter(
    (u) =>
      u.email.toLowerCase().includes(userSearch.toLowerCase()) ||
      (u.phone && u.phone.includes(userSearch)) ||
      u.role.toLowerCase().includes(userSearch.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[var(--ink)]">
            System & Group Settings
          </h1>
          <p className="text-xs sm:text-sm text-[var(--muted-ink)] mt-0.5">
            Configure lending policies, interest calculation modes, late fine rates, and user access
          </p>
        </div>

        {/* Tab Switcher */}
        {isAdmin && (
          <div className="inline-flex rounded-md border border-[var(--border)] p-1 bg-[var(--surface-muted)]">
            <button
              type="button"
              onClick={() => setActiveTab('rules')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded ${
                activeTab === 'rules'
                  ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                  : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
              }`}
            >
              <Sliders className="w-3.5 h-3.5" />
              <span>Group Rules</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('users')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded ${
                activeTab === 'users'
                  ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                  : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
              }`}
            >
              <Users className="w-3.5 h-3.5" />
              <span>Users Directory</span>
            </button>
          </div>
        )}
      </div>

      {/* Tab 1: Group Financial Rules */}
      {activeTab === 'rules' && (
        <div className="space-y-6">
          {/* Group Selector */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Building2 className="w-5 h-5 text-[var(--primary)]" />
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)]">
                  Configuring Group
                </span>
                <p className="font-serif font-bold text-base text-[var(--ink)]">
                  {groups.find((g) => g.id === selectedGroupId)?.name || 'Select a Group'}
                </p>
              </div>
            </div>

            {groups.length > 1 && (
              <select
                value={selectedGroupId}
                onChange={(e) => setSelectedGroupId(e.target.value)}
                className="px-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-medium focus:ring-2 focus:ring-[var(--primary)]"
              >
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Feedback Banners */}
          {settingsSuccess && (
            <div className="p-4 bg-[var(--surface)] border-l-4 border-l-[var(--success)] border border-[var(--border)] rounded flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-[var(--success)] shrink-0" />
              <p className="text-xs text-[var(--success)] font-medium">{settingsSuccess}</p>
            </div>
          )}

          {settingsError && (
            <div className="p-4 bg-[var(--surface)] border-l-4 border-l-[var(--danger)] border border-[var(--border)] rounded flex items-center gap-3">
              <AlertCircle className="w-5 h-5 text-[var(--danger)] shrink-0" />
              <p className="text-xs text-[var(--danger)]">{settingsError}</p>
            </div>
          )}

          {/* Settings Form */}
          <form
            onSubmit={handleSaveSettings}
            className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6 space-y-6"
          >
            <div className="border-b border-[var(--border)] pb-3 flex items-center justify-between">
              <div>
                <h3 className="font-serif font-bold text-base text-[var(--ink)]">
                  Lending & Savings Policies
                </h3>
                <p className="text-xs text-[var(--muted-ink)]">
                  Values will apply to new loan schedules, meetings, and dues calculations
                </p>
              </div>
              {settings?.updated_at && (
                <span className="text-[10px] text-[var(--muted-ink)] font-mono">
                  Updated: {new Date(settings.updated_at).toLocaleDateString()}
                </span>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Monthly Saving Amount */}
              <div>
                <label className="block text-xs font-semibold text-[var(--ink)] mb-1">
                  Mandatory Monthly Savings Amount (₹)
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-2.5 text-xs text-[var(--muted-ink)]">₹</span>
                  <input
                    type="number"
                    step="50"
                    min="0"
                    required
                    value={monthlySaving}
                    onChange={(e) => setMonthlySaving(e.target.value)}
                    disabled={!isLeaderOrAdmin}
                    className="w-full pl-7 pr-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-mono font-medium focus:ring-2 focus:ring-[var(--primary)]"
                  />
                </div>
                <p className="text-[11px] text-[var(--muted-ink)] mt-1">
                  Auto-generated savings due for each active member each monthly cycle
                </p>
              </div>

              {/* Default Interest Rate */}
              <div>
                <label className="block text-xs font-semibold text-[var(--ink)] mb-1">
                  Default Loan Interest Rate (% p.a.)
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="100"
                    required
                    value={interestRate}
                    onChange={(e) => setInterestRate(e.target.value)}
                    disabled={!isLeaderOrAdmin}
                    className="w-full pl-3 pr-7 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-mono font-medium focus:ring-2 focus:ring-[var(--primary)]"
                  />
                  <span className="absolute right-3 top-2.5 text-xs text-[var(--muted-ink)]">%</span>
                </div>
                <p className="text-[11px] text-[var(--muted-ink)] mt-1">
                  Annualized percentage rate for new member credit disbursements
                </p>
              </div>

              {/* Interest Type */}
              <div>
                <label className="block text-xs font-semibold text-[var(--ink)] mb-1">
                  Interest Method
                </label>
                <select
                  value={interestType}
                  onChange={(e) => setInterestType(e.target.value as InterestType)}
                  disabled={!isLeaderOrAdmin}
                  className="w-full px-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-medium focus:ring-2 focus:ring-[var(--primary)]"
                >
                  <option value="REDUCING">Reducing Balance (Diminishing)</option>
                  <option value="FLAT">Flat Rate (Fixed Total)</option>
                </select>
                <p className="text-[11px] text-[var(--muted-ink)] mt-1">
                  SPEC section 6.3 calculation standard
                </p>
              </div>

              {/* Late Fine per day */}
              <div>
                <label className="block text-xs font-semibold text-[var(--ink)] mb-1">
                  Late Fine per Day (₹)
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-2.5 text-xs text-[var(--muted-ink)]">₹</span>
                  <input
                    type="number"
                    step="1"
                    min="0"
                    required
                    value={lateFinePerDay}
                    onChange={(e) => setLateFinePerDay(e.target.value)}
                    disabled={!isLeaderOrAdmin}
                    className="w-full pl-7 pr-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-mono font-medium focus:ring-2 focus:ring-[var(--primary)]"
                  />
                </div>
                <p className="text-[11px] text-[var(--muted-ink)] mt-1">
                  Accrues daily when savings or installments remain unpaid past grace days
                </p>
              </div>

              {/* Grace Days */}
              <div>
                <label className="block text-xs font-semibold text-[var(--ink)] mb-1">
                  Fine Grace Days
                </label>
                <input
                  type="number"
                  min="0"
                  max="60"
                  required
                  value={fineGraceDays}
                  onChange={(e) => setFineGraceDays(parseInt(e.target.value, 10) || 0)}
                  disabled={!isLeaderOrAdmin}
                  className="w-full px-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-mono font-medium focus:ring-2 focus:ring-[var(--primary)]"
                />
                <p className="text-[11px] text-[var(--muted-ink)] mt-1">
                  Days after due date before daily late penalty begins accruing
                </p>
              </div>

              {/* Loan Ceiling Multiplier */}
              <div>
                <label className="block text-xs font-semibold text-[var(--ink)] mb-1">
                  Loan Ceiling Multiplier (x of Savings)
                </label>
                <input
                  type="number"
                  step="0.5"
                  min="1"
                  max="10"
                  required
                  value={loanCeilingMultiplier}
                  onChange={(e) => setLoanCeilingMultiplier(e.target.value)}
                  disabled={!isLeaderOrAdmin}
                  className="w-full px-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-mono font-medium focus:ring-2 focus:ring-[var(--primary)]"
                />
                <p className="text-[11px] text-[var(--muted-ink)] mt-1">
                  Maximum loan principal allowed per member (e.g. 3.0x member savings balance)
                </p>
              </div>
            </div>

            {isLeaderOrAdmin && (
              <div className="pt-4 border-t border-[var(--border)] flex justify-end">
                <button
                  type="submit"
                  disabled={savingSettings}
                  className="inline-flex items-center gap-2 px-5 py-2 text-xs font-semibold rounded-md bg-[var(--primary)] text-white hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm"
                >
                  <Save className="w-4 h-4" />
                  <span>{savingSettings ? 'Saving Settings...' : 'Save Group Policies'}</span>
                </button>
              </div>
            )}
          </form>
        </div>
      )}

      {/* Tab 2: Users Directory (ADMIN Only) */}
      {isAdmin && activeTab === 'users' && (
        <div className="space-y-4">
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h3 className="font-serif font-bold text-base text-[var(--ink)]">
                Platform User Accounts
              </h3>
              <p className="text-xs text-[var(--muted-ink)]">
                Manage system credentials, group leader permissions, and member portal access
              </p>
            </div>

            <div className="relative">
              <input
                type="text"
                placeholder="Search email, phone, role..."
                value={userSearch}
                onChange={(e) => setUserSearch(e.target.value)}
                className="pl-8 pr-3 py-1.5 text-xs bg-[var(--surface-muted)] border border-[var(--border)] rounded text-[var(--ink)] w-64 focus:ring-2 focus:ring-[var(--primary)]"
              />
              <Users className="w-3.5 h-3.5 text-[var(--muted-ink)] absolute left-2.5 top-2" />
            </div>
          </div>

          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--surface-muted)] text-[var(--muted-ink)] font-semibold uppercase">
                    <th className="py-2.5 px-4">User Email</th>
                    <th className="py-2.5 px-4">Phone</th>
                    <th className="py-2.5 px-4">System Role</th>
                    <th className="py-2.5 px-4 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {usersLoading ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-[var(--muted-ink)]">
                        Loading directory...
                      </td>
                    </tr>
                  ) : filteredUsers.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-8 text-center text-[var(--muted-ink)]">
                        No users match search criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredUsers.map((u) => (
                      <tr key={u.id} className="hover:bg-[var(--surface-muted)]">
                        <td className="py-3 px-4 font-mono font-medium text-[var(--ink)]">
                          {u.email}
                        </td>
                        <td className="py-3 px-4 font-mono text-[var(--muted-ink)]">
                          {u.phone || '-'}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${
                              u.role === 'ADMIN'
                                ? 'bg-[var(--accent)] text-white'
                                : u.role === 'GROUP_LEADER'
                                ? 'bg-[var(--primary)] text-white'
                                : 'bg-[var(--surface-muted)] text-[var(--ink)]'
                            }`}
                          >
                            {u.role}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span
                            className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${
                              u.is_active
                                ? 'bg-[var(--primary-tint)] text-[var(--primary)]'
                                : 'bg-[var(--danger)] text-white'
                            }`}
                          >
                            {u.is_active ? 'ACTIVE' : 'INACTIVE'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
