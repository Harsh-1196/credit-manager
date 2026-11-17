import React, { useEffect, useState } from 'react';
import { useAuth } from '../../lib/auth/AuthContext';
import { apiClient } from '../../lib/api/client';
import type { DashboardResponse, GroupResponse } from '../../lib/api/types';
import { formatIndianAbbreviated, formatIndianMoney } from '../../lib/money';
import {
  SavingsTrendChart,
  AgingBucketsChart,
  DisbursalsVsRepaymentsChart,
} from './DashboardCharts';
import {
  Wallet,
  Coins,
  TrendingUp,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
} from 'lucide-react';
import { Link } from 'react-router-dom';

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [groups, setGroups] = useState<GroupResponse[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Load groups for selector if admin or leader
  useEffect(() => {
    if (user?.role && user.role !== 'MEMBER') {
      apiClient.groups
        .list()
        .then((res) => {
          setGroups(res.items);
          if (res.items.length > 0 && !selectedGroupId) {
            setSelectedGroupId(res.items[0].id);
          }
        })
        .catch(() => {});
    }
  }, [user]);

  // Load dashboard data
  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError(null);

    const params: { shg_id?: string } = {};
    if (selectedGroupId && user?.role !== 'MEMBER') {
      params.shg_id = selectedGroupId;
    }

    apiClient.dashboard
      .get(params)
      .then((res) => {
        if (isMounted) {
          setData(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to load dashboard data');
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedGroupId, user]);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse p-2">
        <div className="h-8 bg-[var(--surface-muted)] rounded w-64"></div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="h-32 bg-[var(--surface-muted)] rounded-lg"></div>
          <div className="h-32 bg-[var(--surface-muted)] rounded-lg"></div>
          <div className="h-32 bg-[var(--surface-muted)] rounded-lg"></div>
          <div className="h-32 bg-[var(--surface-muted)] rounded-lg"></div>
        </div>
        <div className="h-72 bg-[var(--surface-muted)] rounded-lg"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-6 text-center">
        <AlertTriangle className="w-8 h-8 text-[var(--accent)] mx-auto mb-2" />
        <h3 className="font-serif font-bold text-lg text-[var(--ink)]">Unable to load dashboard</h3>
        <p className="text-xs text-[var(--muted-ink)] mt-1">{error || 'Unknown error occurred.'}</p>
        <button
          type="button"
          onClick={() => setSelectedGroupId((prev) => prev)}
          className="mt-4 px-4 py-2 bg-[var(--primary)] text-white text-xs font-semibold rounded hover:opacity-90"
        >
          Try Again
        </button>
      </div>
    );
  }

  /* -------------------------------------------------------------------------- */
  /* MEMBER DASHBOARD VIEW                                                      */
  /* -------------------------------------------------------------------------- */
  if (data.role === 'MEMBER' && data.member_dashboard) {
    const mem = data.member_dashboard.member;
    const passbook = (data.member_dashboard.passbook_entries || []) as any[];
    const activeLoans = (data.member_dashboard.active_loans || []) as any[];

    const savingsAbbr = formatIndianAbbreviated(mem.total_savings_balance);
    const loansOutstandingAbbr = formatIndianAbbreviated(mem.current_outstanding_principal);

    return (
      <div className="space-y-8 max-w-7xl mx-auto pb-10">
        {/* Welcome Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-[var(--border)] pb-4">
          <div>
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[var(--ink)]">
              Welcome, {mem.name}
            </h1>
            <p className="text-xs sm:text-sm text-[var(--muted-ink)] mt-0.5">
              Member ID: <span className="font-mono">{mem.member_id.slice(0, 8)}</span> • Joined{' '}
              {mem.join_date}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/loans/apply"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-md bg-[var(--primary)] text-white hover:opacity-90 transition-opacity"
            >
              <Coins className="w-4 h-4" />
              Apply for Loan
            </Link>
          </div>
        </div>

        {/* Member Key Figures */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Card 1: Savings */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 shadow-sm border-l-4 border-l-[var(--primary)]">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)] flex items-center gap-1.5">
              <Wallet className="w-4 h-4 text-[var(--primary)]" /> Total Savings Balance
            </span>
            <div
              className="mt-2 font-serif text-3xl sm:text-4xl font-bold tracking-tight text-[var(--ink)] tabular-nums cursor-help"
              title={`Full Balance: ${savingsAbbr.full}`}
            >
              {savingsAbbr.abbreviated}
            </div>
            <p className="text-xs text-[var(--muted-ink)] mt-1">Full: {savingsAbbr.full}</p>
          </div>

          {/* Card 2: Loan Outstanding */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 shadow-sm border-l-4 border-l-[var(--accent)]">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)] flex items-center gap-1.5">
              <Coins className="w-4 h-4 text-[var(--accent)]" /> Loan Principal Outstanding
            </span>
            <div
              className="mt-2 font-serif text-3xl sm:text-4xl font-bold tracking-tight text-[var(--ink)] tabular-nums cursor-help"
              title={`Full Outstanding: ${loansOutstandingAbbr.full}`}
            >
              {loansOutstandingAbbr.abbreviated}
            </div>
            <p className="text-xs text-[var(--muted-ink)] mt-1">Active Loans: {activeLoans.length}</p>
          </div>

          {/* Card 3: Group & Status */}
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 shadow-sm border-l-4 border-l-[var(--success)]">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)] flex items-center gap-1.5">
              <Clock className="w-4 h-4 text-[var(--success)]" /> Group & Status
            </span>
            <div className="mt-2 font-serif text-2xl sm:text-3xl font-bold tracking-tight text-[var(--ink)] truncate">
              {mem.shg_name}
            </div>
            <p className="text-xs text-[var(--muted-ink)] mt-1">
              Member Status: <span className="font-semibold text-[var(--success)]">{mem.status}</span>
            </p>
          </div>
        </div>

        {/* Member Active Loans Table */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5">
          <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] mb-4">
            <h3 className="font-serif font-bold text-base text-[var(--ink)]">My Active Loans</h3>
            <span className="text-xs text-[var(--muted-ink)]">{activeLoans.length} active</span>
          </div>

          {activeLoans.length === 0 ? (
            <p className="text-xs text-[var(--muted-ink)] py-4 text-center">
              You currently have no active loans.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                    <th className="py-2 px-3">Loan #</th>
                    <th className="py-2 px-3 text-right">Principal</th>
                    <th className="py-2 px-3 text-right">Outstanding</th>
                    <th className="py-2 px-3 text-right">Rate</th>
                    <th className="py-2 px-3 text-center">Status</th>
                    <th className="py-2 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {activeLoans.map((l) => (
                    <tr key={l.loan_id} className="hover:bg-[var(--surface-muted)]">
                      <td className="py-2.5 px-3 font-mono font-medium">{l.loan_number}</td>
                      <td className="py-2.5 px-3 text-right font-mono">{formatIndianMoney(l.principal)}</td>
                      <td className="py-2.5 px-3 text-right font-mono font-semibold text-[var(--accent)]">
                        {formatIndianMoney(l.outstanding_principal)}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono">{l.interest_rate}%</td>
                      <td className="py-2.5 px-3 text-center">
                        <span className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold bg-[var(--primary-tint)] text-[var(--primary)]">
                          {l.status}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right">
                        <Link
                          to={`/loans/${l.loan_id}`}
                          className="text-[var(--primary)] font-semibold hover:underline"
                        >
                          View Schedule →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Member Passbook Recent Transactions */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5">
          <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] mb-4">
            <div>
              <h3 className="font-serif font-bold text-base text-[var(--ink)]">Recent Passbook Activity</h3>
              <p className="text-xs text-[var(--muted-ink)]">Latest transactions on your member account</p>
            </div>
            <Link
              to={`/members/${mem.member_id}`}
              className="text-xs font-semibold text-[var(--primary)] hover:underline flex items-center gap-1"
            >
              Full Passbook <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {passbook.length === 0 ? (
            <p className="text-xs text-[var(--muted-ink)] py-4 text-center">
              No transactions recorded in passbook yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                    <th className="py-2 px-3">Date</th>
                    <th className="py-2 px-3">Description</th>
                    <th className="py-2 px-3 text-right">Debit</th>
                    <th className="py-2 px-3 text-right">Credit</th>
                    <th className="py-2 px-3 text-right">Running Balance</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {passbook.slice(0, 5).map((entry) => (
                    <tr key={entry.entry_id} className="hover:bg-[var(--surface-muted)]">
                      <td className="py-2.5 px-3 font-mono">{entry.date}</td>
                      <td className="py-2.5 px-3">{entry.particulars}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-[var(--accent)]">
                        {parseFloat(entry.debit) > 0 ? formatIndianMoney(entry.debit) : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono text-[var(--primary)]">
                        {parseFloat(entry.credit) > 0 ? formatIndianMoney(entry.credit) : '-'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-mono font-semibold">
                        {formatIndianMoney(entry.balance)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    );
  }

  /* -------------------------------------------------------------------------- */
  /* GROUP DASHBOARD VIEW (ADMIN / GROUP_LEADER / AUDITOR)                      */
  /* -------------------------------------------------------------------------- */
  const gd = data.group_dashboard;
  if (!gd) {
    return (
      <div className="p-6 text-center text-xs text-[var(--muted-ink)]">
        No group dashboard data available.
      </div>
    );
  }

  const figs = gd.figures;
  const activeLoansCount = gd.aging_buckets.reduce((acc, b) => acc + b.count, 0);
  const corpusAbbr = formatIndianAbbreviated(figs.total_corpus);
  const outstandingAbbr = formatIndianAbbreviated(figs.outstanding_principal);
  const overdueAbbr = formatIndianAbbreviated(figs.overdue_amount);
  const repaymentRateStr = `${parseFloat(figs.repayment_rate).toFixed(1)}%`;

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      {/* Group Header & Switcher */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[var(--ink)]">
              {gd.shg_name}
            </h1>
            <span className="inline-block px-2 py-0.5 text-[10px] font-mono font-semibold rounded bg-[var(--primary-tint)] text-[var(--primary)]">
              {activeLoansCount} Active Loans
            </span>
          </div>
          <p className="text-xs sm:text-sm text-[var(--muted-ink)] mt-0.5">
            Overview • As of {new Date().toLocaleDateString('en-IN', { dateStyle: 'medium' })}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {groups.length > 1 && (
            <div className="flex items-center gap-2">
              <label htmlFor="group-select" className="text-xs text-[var(--muted-ink)] font-medium">
                Group:
              </label>
              <select
                id="group-select"
                value={selectedGroupId}
                onChange={(e) => setSelectedGroupId(e.target.value)}
                className="px-2.5 py-1.5 text-xs bg-[var(--surface)] border border-[var(--border)] rounded font-medium text-[var(--ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              >
                {groups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <Link
            to="/reports"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--ink)] hover:bg-[var(--surface-muted)] transition-colors"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-[var(--primary)]" />
            Full Reports
          </Link>
        </div>
      </div>

      {/* Headline Key Figures: Staggered, Non-Equal Layout (SPEC 12.5 Screen 2) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Figure 1: Group Corpus (Dominant Hero Card) */}
        <div className="bg-[var(--surface)] border-2 border-[var(--primary)] rounded-lg p-5 shadow-sm relative overflow-hidden">
          <div className="absolute top-0 right-0 w-16 h-16 bg-[var(--primary-tint)] rounded-bl-full -mr-4 -mt-4 opacity-50" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)] flex items-center gap-1.5">
            <Wallet className="w-4 h-4 text-[var(--primary)]" /> Total Group Corpus
          </span>
          <div
            className="mt-2 font-serif text-3xl sm:text-4xl font-bold tracking-tight text-[var(--primary)] tabular-nums cursor-help"
            title={`Full Corpus: ${corpusAbbr.full}`}
          >
            {corpusAbbr.abbreviated}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-[var(--muted-ink)]">
            <span>Full: {corpusAbbr.full}</span>
            <span className="font-medium text-[var(--ink)]">Cash + Bank</span>
          </div>
        </div>

        {/* Figure 2: Outstanding Principal */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 shadow-sm border-t-4 border-t-[var(--accent)]">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)] flex items-center gap-1.5">
            <Coins className="w-4 h-4 text-[var(--accent)]" /> Outstanding Principal
          </span>
          <div
            className="mt-2 font-serif text-3xl sm:text-4xl font-bold tracking-tight text-[var(--ink)] tabular-nums cursor-help"
            title={`Full Outstanding: ${outstandingAbbr.full}`}
          >
            {outstandingAbbr.abbreviated}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-[var(--muted-ink)]">
            <span>Full: {outstandingAbbr.full}</span>
            <span>{activeLoansCount} loans</span>
          </div>
        </div>

        {/* Figure 3: Repayment Rate */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 shadow-sm border-t-4 border-t-[var(--success)]">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)] flex items-center gap-1.5">
            <TrendingUp className="w-4 h-4 text-[var(--success)]" /> Repayment Rate
          </span>
          <div
            className="mt-2 font-serif text-3xl sm:text-4xl font-bold tracking-tight text-[var(--success)] tabular-nums cursor-help"
            title={`Precise: ${figs.repayment_rate}%`}
          >
            {repaymentRateStr}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-[var(--muted-ink)]">
            <span>On-time recovery</span>
            <span className="text-[var(--success)] font-medium">Healthy</span>
          </div>
        </div>

        {/* Figure 4: Overdue Amount */}
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 shadow-sm border-t-4 border-t-[var(--danger)]">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)] flex items-center gap-1.5">
            <AlertTriangle className="w-4 h-4 text-[var(--danger)]" /> Overdue Amount
          </span>
          <div
            className="mt-2 font-serif text-3xl sm:text-4xl font-bold tracking-tight text-[var(--danger)] tabular-nums cursor-help"
            title={`Full Overdue: ${overdueAbbr.full}`}
          >
            {overdueAbbr.abbreviated}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-[var(--muted-ink)]">
            <span>Full: {overdueAbbr.full}</span>
            <span className="text-[var(--danger)] font-medium">Requires follow-up</span>
          </div>
        </div>
      </div>

      {/* Collections Due Section */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-[var(--border)] mb-4">
          <div>
            <h3 className="font-serif font-bold text-base text-[var(--ink)]">Upcoming Collections Due</h3>
            <p className="text-xs text-[var(--muted-ink)]">
              Scheduled savings, EMI installments and fines due for collection
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-semibold text-[var(--primary)] bg-[var(--surface-muted)] px-2 py-1 rounded">
              {gd.collections_due.length} Items Listed
            </span>
          </div>
        </div>

        {gd.collections_due.length === 0 ? (
          <div className="py-8 text-center text-xs text-[var(--muted-ink)]">
            <CheckCircle2 className="w-8 h-8 text-[var(--success)] mx-auto mb-1 opacity-70" />
            No pending collections due at this moment. All dues are up to date!
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                  <th className="py-2 px-3">Member Name</th>
                  <th className="py-2 px-3 text-right">Savings Due</th>
                  <th className="py-2 px-3 text-right">EMI Due</th>
                  <th className="py-2 px-3 text-right">Fines Due</th>
                  <th className="py-2 px-3 text-right">Total Payable</th>
                  <th className="py-2 px-3 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {gd.collections_due.map((item) => (
                  <tr key={item.member_id} className="hover:bg-[var(--surface-muted)]">
                    <td className="py-2.5 px-3 font-medium text-[var(--ink)]">
                      <Link
                        to={`/members/${item.member_id}`}
                        className="hover:text-[var(--primary)] hover:underline"
                      >
                        {item.member_name}
                      </Link>
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono">
                      {formatIndianMoney(item.savings_due)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono">
                      {formatIndianMoney(item.emi_due)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-[var(--danger)]">
                      {parseFloat(item.fines) > 0 ? formatIndianMoney(item.fines) : '-'}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-[var(--ink)]">
                      {formatIndianMoney(item.total_due)}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${
                          parseFloat(item.arrears) > 0
                            ? 'bg-[var(--danger)] text-white'
                            : 'bg-[var(--surface-muted)] text-[var(--ink)]'
                        }`}
                      >
                        {parseFloat(item.arrears) > 0 ? 'OVERDUE' : 'DUE'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Restyled Recharts Section (Grid of Charts with Data Table Toggles) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SavingsTrendChart data={gd.savings_trend} />
        <AgingBucketsChart data={gd.aging_buckets} />
      </div>

      <div className="grid grid-cols-1 gap-6">
        <DisbursalsVsRepaymentsChart data={gd.disbursals_vs_repayments} />
      </div>
    </div>
  );
};
