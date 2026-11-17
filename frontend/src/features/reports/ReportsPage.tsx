import React, { useState, useEffect } from 'react';
import { apiClient } from '../../lib/api/client';
import type {
  GroupResponse,
  MemberResponse,
  GroupDashboardReportResponse,
  MemberStatementReportResponse,
  GroupLedgerReportResponse,
  LoanPortfolioReportResponse,
} from '../../lib/api/types';
import { formatIndianMoney } from '../../lib/money';
import {
  Download,
  FileSpreadsheet,
  Filter,
  CheckCircle2,
  AlertCircle,
  Scale,
} from 'lucide-react';

type ReportType = 'group-dashboard' | 'member-statement' | 'group-ledger' | 'loan-portfolio';

export const ReportsPage: React.FC = () => {
  const [reportType, setReportType] = useState<ReportType>('group-dashboard');
  const [groups, setGroups] = useState<GroupResponse[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [members, setMembers] = useState<MemberResponse[]>([]);
  const [selectedMemberId, setSelectedMemberId] = useState<string>('');

  // Report Preview Data
  const [groupDashboardData, setGroupDashboardData] = useState<GroupDashboardReportResponse | null>(null);
  const [memberStatementData, setMemberStatementData] = useState<MemberStatementReportResponse | null>(null);
  const [groupLedgerData, setGroupLedgerData] = useState<GroupLedgerReportResponse | null>(null);
  const [loanPortfolioData, setLoanPortfolioData] = useState<LoanPortfolioReportResponse | null>(null);

  const [loading, setLoading] = useState<boolean>(false);
  const [exporting, setExporting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // 1. Load initial groups
  useEffect(() => {
    apiClient.groups
      .list()
      .then((res) => {
        setGroups(res.items);
        if (res.items.length > 0 && !selectedGroupId) {
          setSelectedGroupId(res.items[0].id);
        }
      })
      .catch((err) => setError(err.message || 'Failed to load groups'));
  }, []);

  // 2. Load members when group changes
  useEffect(() => {
    if (selectedGroupId) {
      apiClient.members
        .listByGroup(selectedGroupId)
        .then((res) => {
          setMembers(res.items);
          if (res.items.length > 0) {
            setSelectedMemberId(res.items[0].id);
          } else {
            setSelectedMemberId('');
          }
        })
        .catch(() => setMembers([]));
    }
  }, [selectedGroupId]);

  // 3. Load report preview data
  const fetchReport = async () => {
    if (!selectedGroupId && reportType !== 'member-statement') return;
    if (reportType === 'member-statement' && !selectedMemberId) return;

    setLoading(true);
    setError(null);

    try {
      if (reportType === 'group-dashboard') {
        const res = await apiClient.reports.getGroupDashboard(selectedGroupId);
        setGroupDashboardData(res);
      } else if (reportType === 'member-statement') {
        const res = await apiClient.reports.getMemberStatement(selectedMemberId);
        setMemberStatementData(res);
      } else if (reportType === 'group-ledger') {
        const res = await apiClient.reports.getGroupLedger(selectedGroupId);
        setGroupLedgerData(res);
      } else if (reportType === 'loan-portfolio') {
        const res = await apiClient.reports.getLoanPortfolio(selectedGroupId);
        setLoanPortfolioData(res);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to generate report preview.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedGroupId) {
      fetchReport();
    }
  }, [reportType, selectedGroupId, selectedMemberId]);

  // 4. Download CSV Export
  const handleExportCsv = async () => {
    setExporting(true);
    try {
      let blob: Blob | null = null;
      let filename = `report_${reportType}_${new Date().toISOString().split('T')[0]}.csv`;

      if (reportType === 'group-dashboard') {
        blob = await apiClient.reports.exportGroupDashboardCsv(selectedGroupId);
        filename = `group_dashboard_${selectedGroupId.slice(0, 8)}.csv`;
      } else if (reportType === 'member-statement') {
        blob = await apiClient.reports.exportMemberStatementCsv(selectedMemberId);
        filename = `member_statement_${selectedMemberId.slice(0, 8)}.csv`;
      } else if (reportType === 'group-ledger') {
        blob = await apiClient.reports.exportGroupLedgerCsv(selectedGroupId);
        filename = `group_ledger_${selectedGroupId.slice(0, 8)}.csv`;
      } else if (reportType === 'loan-portfolio') {
        blob = await apiClient.reports.exportLoanPortfolioCsv(selectedGroupId);
        filename = `loan_portfolio_${selectedGroupId.slice(0, 8)}.csv`;
      }

      if (blob) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (err: any) {
      alert(`Export failed: ${err.message || 'Unknown error'}`);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-[var(--border)] pb-4">
        <div>
          <h1 className="font-serif text-2xl sm:text-3xl font-bold text-[var(--ink)]">
            Reports & Financial Statements
          </h1>
          <p className="text-xs sm:text-sm text-[var(--muted-ink)] mt-0.5">
            Audit-grade double-entry ledger summaries, member statements, and loan portfolio exports
          </p>
        </div>

        <button
          type="button"
          onClick={handleExportCsv}
          disabled={exporting || loading}
          className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-md bg-[var(--primary)] text-white hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm self-start sm:self-auto"
        >
          <Download className="w-4 h-4" />
          <span>{exporting ? 'Generating CSV...' : 'Export to CSV'}</span>
        </button>
      </div>

      {/* Filter Bar */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Report Type */}
          <div>
            <label htmlFor="report-type-select" className="block text-xs font-semibold text-[var(--muted-ink)] mb-1">
              Report Type
            </label>
            <select
              id="report-type-select"
              value={reportType}
              onChange={(e) => setReportType(e.target.value as ReportType)}
              className="w-full px-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-medium focus:ring-2 focus:ring-[var(--primary)]"
            >
              <option value="group-dashboard">Group Dashboard Summary</option>
              <option value="member-statement">Member Statement & Passbook</option>
              <option value="group-ledger">Group Ledger & Trial Balance</option>
              <option value="loan-portfolio">Loan Portfolio & Aging (PAR)</option>
            </select>
          </div>

          {/* Group Selector */}
          <div>
            <label htmlFor="group-select" className="block text-xs font-semibold text-[var(--muted-ink)] mb-1">
              Select Group (SHG)
            </label>
            <select
              id="group-select"
              value={selectedGroupId}
              onChange={(e) => setSelectedGroupId(e.target.value)}
              className="w-full px-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-medium focus:ring-2 focus:ring-[var(--primary)]"
            >
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>

          {/* Member Selector (conditional) */}
          {reportType === 'member-statement' && (
            <div>
              <label htmlFor="member-select" className="block text-xs font-semibold text-[var(--muted-ink)] mb-1">
                Select Member
              </label>
              <select
                id="member-select"
                value={selectedMemberId}
                onChange={(e) => setSelectedMemberId(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-[var(--surface)] border border-[var(--border)] rounded text-[var(--ink)] font-medium focus:ring-2 focus:ring-[var(--primary)]"
              >
                {members.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.full_name} ({m.phone})
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Refresh Action */}
          <div className="flex items-end">
            <button
              type="button"
              onClick={fetchReport}
              disabled={loading}
              className="w-full py-2 px-3 text-xs font-medium rounded border border-[var(--border)] bg-[var(--surface-muted)] text-[var(--ink)] hover:bg-[var(--surface)] transition-colors flex items-center justify-center gap-1.5"
            >
              <Filter className="w-3.5 h-3.5 text-[var(--muted-ink)]" />
              <span>{loading ? 'Refreshing...' : 'Apply Filters'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div className="p-4 bg-[var(--surface)] border-l-4 border-l-[var(--danger)] border border-[var(--border)] rounded flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-[var(--danger)] shrink-0" />
          <p className="text-xs text-[var(--danger)]">{error}</p>
        </div>
      )}

      {/* Preview Section */}
      <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5">
        <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] mb-4">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="w-4 h-4 text-[var(--primary)]" />
            <h2 className="font-serif font-bold text-base text-[var(--ink)]">Live Report Preview</h2>
          </div>
          <span className="text-xs text-[var(--muted-ink)] font-mono">Format: Table / Tabular</span>
        </div>

        {loading ? (
          <div className="py-16 text-center text-xs text-[var(--muted-ink)] animate-pulse">
            Calculating financial totals and fetching lines...
          </div>
        ) : (
          <div>
            {/* 1. Group Dashboard Preview */}
            {reportType === 'group-dashboard' && groupDashboardData && (
              <div className="space-y-6">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-[var(--surface-muted)] p-4 rounded-lg">
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Total Corpus
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--primary)]">
                      {formatIndianMoney(groupDashboardData.figures.total_corpus)}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Total Savings
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--ink)]">
                      {formatIndianMoney(groupDashboardData.figures.total_savings)}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Principal Outstanding
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--accent)]">
                      {formatIndianMoney(groupDashboardData.figures.outstanding_principal)}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Repayment Rate
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--success)]">
                      {groupDashboardData.figures.repayment_rate}%
                    </div>
                  </div>
                </div>

                <h4 className="font-semibold text-xs text-[var(--ink)] uppercase tracking-wider">
                  Upcoming Collections Due
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                        <th className="py-2 px-3">Member</th>
                        <th className="py-2 px-3 text-right">Savings Due</th>
                        <th className="py-2 px-3 text-right">EMI Due</th>
                        <th className="py-2 px-3 text-right">Fines Due</th>
                        <th className="py-2 px-3 text-right">Total Payable</th>
                        <th className="py-2 px-3 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {groupDashboardData.collections_due.map((item) => (
                        <tr key={item.member_id} className="hover:bg-[var(--surface-muted)]">
                          <td className="py-2 px-3 font-medium">{item.member_name}</td>
                          <td className="py-2 px-3 text-right font-mono">
                            {formatIndianMoney(item.savings_due)}
                          </td>
                          <td className="py-2 px-3 text-right font-mono">
                            {formatIndianMoney(item.emi_due)}
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-[var(--danger)]">
                            {parseFloat(item.fines) > 0 ? formatIndianMoney(item.fines) : '-'}
                          </td>
                          <td className="py-2 px-3 text-right font-mono font-bold">
                            {formatIndianMoney(item.total_due)}
                          </td>
                          <td className="py-2 px-3 text-center">
                            <span className="inline-block px-2 py-0.5 rounded text-[10px] bg-[var(--surface-muted)]">
                              {parseFloat(item.arrears) > 0 ? 'OVERDUE' : 'DUE'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* 2. Member Statement Preview */}
            {reportType === 'member-statement' && memberStatementData && (
              <div className="space-y-6">
                <div className="bg-[var(--surface-muted)] p-4 rounded-lg flex flex-col sm:flex-row justify-between gap-4">
                  <div>
                    <h3 className="font-serif font-bold text-lg text-[var(--ink)]">
                      {memberStatementData.member.name}
                    </h3>
                    <p className="text-xs text-[var(--muted-ink)]">
                      Phone: {memberStatementData.member.phone} • Joined:{' '}
                      {memberStatementData.member.joined_on}
                    </p>
                  </div>
                  <div className="flex gap-6">
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                        Savings Balance
                      </span>
                      <div className="font-serif text-lg font-bold text-[var(--primary)]">
                        {formatIndianMoney(memberStatementData.member.total_savings_balance)}
                      </div>
                    </div>
                    <div>
                      <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                        Loan Outstanding
                      </span>
                      <div className="font-serif text-lg font-bold text-[var(--accent)]">
                        {formatIndianMoney(memberStatementData.member.total_loan_outstanding)}
                      </div>
                    </div>
                  </div>
                </div>

                <h4 className="font-semibold text-xs text-[var(--ink)] uppercase tracking-wider">
                  Passbook Ledger History
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                        <th className="py-2 px-3">Date</th>
                        <th className="py-2 px-3">Particulars</th>
                        <th className="py-2 px-3 text-right">Debit</th>
                        <th className="py-2 px-3 text-right">Credit</th>
                        <th className="py-2 px-3 text-right">Balance</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {memberStatementData.passbook_entries.map((p) => (
                        <tr key={p.entry_id} className="hover:bg-[var(--surface-muted)]">
                          <td className="py-2 px-3 font-mono">{p.date}</td>
                          <td className="py-2 px-3">{p.particulars}</td>
                          <td className="py-2 px-3 text-right font-mono text-[var(--accent)]">
                            {parseFloat(p.debit) > 0 ? formatIndianMoney(p.debit) : '-'}
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-[var(--primary)]">
                            {parseFloat(p.credit) > 0 ? formatIndianMoney(p.credit) : '-'}
                          </td>
                          <td className="py-2 px-3 text-right font-mono font-bold">
                            {formatIndianMoney(p.balance)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* 3. Group Ledger & Trial Balance Preview */}
            {reportType === 'group-ledger' && groupLedgerData && (
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-xs text-[var(--ink)] uppercase tracking-wider flex items-center gap-1.5">
                    <Scale className="w-4 h-4 text-[var(--primary)]" /> Trial Balance
                  </h4>
                  <span className="text-xs text-[var(--success)] font-medium flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> Balanced Double-Entry
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                        <th className="py-2 px-3">Account Code</th>
                        <th className="py-2 px-3">Account Name</th>
                        <th className="py-2 px-3">Type</th>
                        <th className="py-2 px-3 text-right">Debit Balance</th>
                        <th className="py-2 px-3 text-right">Credit Balance</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {groupLedgerData.trial_balance.map((tb) => (
                        <tr key={tb.account_id} className="hover:bg-[var(--surface-muted)]">
                          <td className="py-2 px-3 font-mono font-medium">{tb.account_code}</td>
                          <td className="py-2 px-3">{tb.account_name}</td>
                          <td className="py-2 px-3 font-mono text-[10px] text-[var(--muted-ink)]">
                            {tb.account_type}
                          </td>
                          <td className="py-2 px-3 text-right font-mono">
                            {parseFloat(tb.debit_balance) > 0
                              ? formatIndianMoney(tb.debit_balance)
                              : '-'}
                          </td>
                          <td className="py-2 px-3 text-right font-mono">
                            {parseFloat(tb.credit_balance) > 0
                              ? formatIndianMoney(tb.credit_balance)
                              : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-[var(--ink)] font-bold text-[var(--ink)] bg-[var(--surface-muted)]">
                        <td className="py-2.5 px-3" colSpan={3}>
                          Total Trial Balance
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono">
                          {formatIndianMoney(
                            groupLedgerData.trial_balance.reduce(
                              (sum, row) => sum + (parseFloat(row.debit_balance) || 0),
                              0
                            )
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono">
                          {formatIndianMoney(
                            groupLedgerData.trial_balance.reduce(
                              (sum, row) => sum + (parseFloat(row.credit_balance) || 0),
                              0
                            )
                          )}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}

            {/* 4. Loan Portfolio Preview */}
            {reportType === 'loan-portfolio' && loanPortfolioData && (
              <div className="space-y-6">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 bg-[var(--surface-muted)] p-4 rounded-lg">
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Active Loans
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--ink)]">
                      {loanPortfolioData.active_loans_count}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Total Disbursed
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--primary)]">
                      {formatIndianMoney(loanPortfolioData.total_disbursed_principal)}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Total Outstanding
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--accent)]">
                      {formatIndianMoney(loanPortfolioData.total_outstanding_principal)}
                    </div>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      PAR Overdue
                    </span>
                    <div className="font-serif text-lg font-bold text-[var(--danger)]">
                      {formatIndianMoney(loanPortfolioData.total_overdue_principal)}
                    </div>
                  </div>
                </div>

                <h4 className="font-semibold text-xs text-[var(--ink)] uppercase tracking-wider">
                  Loan Portfolio Registry
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                        <th className="py-2 px-3">Loan #</th>
                        <th className="py-2 px-3">Borrower</th>
                        <th className="py-2 px-3 text-right">Principal</th>
                        <th className="py-2 px-3 text-right">Outstanding</th>
                        <th className="py-2 px-3 text-right">Overdue</th>
                        <th className="py-2 px-3 text-center">Aging Bracket</th>
                        <th className="py-2 px-3 text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border)]">
                      {loanPortfolioData.loans.map((l) => (
                        <tr key={l.loan_id} className="hover:bg-[var(--surface-muted)]">
                          <td className="py-2 px-3 font-mono font-medium">{l.loan_number}</td>
                          <td className="py-2 px-3">{l.borrower_name}</td>
                          <td className="py-2 px-3 text-right font-mono">
                            {formatIndianMoney(l.principal)}
                          </td>
                          <td className="py-2 px-3 text-right font-mono font-bold text-[var(--accent)]">
                            {formatIndianMoney(l.outstanding_principal)}
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-[var(--danger)]">
                            {parseFloat(l.overdue_principal) > 0
                              ? formatIndianMoney(l.overdue_principal)
                              : '-'}
                          </td>
                          <td className="py-2 px-3 text-center">
                            <span className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold bg-[var(--surface-muted)] text-[var(--ink)]">
                              {l.aging_bucket}
                            </span>
                          </td>
                          <td className="py-2 px-3 text-center">
                            <span className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold bg-[var(--primary-tint)] text-[var(--primary)]">
                              {l.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
