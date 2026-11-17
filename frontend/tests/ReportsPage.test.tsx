import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { ReportsPage } from '../src/features/reports/ReportsPage';
import { apiClient } from '../src/lib/api/client';
import * as AuthContextModule from '../src/lib/auth/AuthContext';
import type {
  GroupDashboardReportResponse,
  GroupLedgerReportResponse,
  LoanPortfolioReportResponse,
} from '../src/lib/api/types';

describe('Screen 10: Reports & Financial Statements', () => {
  const mockGroup = {
    id: 'g0000000-0000-0000-0000-000000000001',
    name: 'Udaan Mahila Mandal',
    village: 'Rampur',
    district: 'Varanasi',
    formation_date: '2025-01-01',
    meeting_day: 'MONDAY',
    meeting_frequency: 'MONTHLY',
    status: 'ACTIVE',
  };

  const groupDashboardReport: GroupDashboardReportResponse = {
    shg_id: mockGroup.id,
    shg_name: mockGroup.name,
    as_of_date: '2026-03-01',
    figures: {
      total_corpus: '50000.00',
      total_savings: '20000.00',
      outstanding_principal: '30000.00',
      interest_earned: '1800.00',
      repayment_rate: '98.5',
      overdue_amount: '0.00',
      next_meeting_date: '2026-03-10',
      collections_due_next_meeting: '5000.00',
    },
    collections_due: [
      {
        member_id: 'm1',
        member_name: 'Radha Devi',
        savings_due: '500.00',
        emi_due: '1000.00',
        arrears: '0.00',
        fines: '0.00',
        total_due: '1500.00',
      },
    ],
    aging_buckets: [],
    savings_trend: [],
    disbursals_vs_repayments: [],
  };

  const groupLedgerReport: GroupLedgerReportResponse = {
    shg_id: mockGroup.id,
    shg_name: mockGroup.name,
    as_of_date: '2026-03-01',
    trial_balance: [
      {
        account_id: 'a1',
        account_code: '1000',
        account_name: 'Cash in Hand',
        account_type: 'ASSET',
        debit_balance: '50000.00',
        credit_balance: '0.00',
      },
      {
        account_id: 'a2',
        account_code: '3000',
        account_name: 'Group Corpus Capital',
        account_type: 'EQUITY',
        debit_balance: '0.00',
        credit_balance: '50000.00',
      },
    ],
    journal_entries: [],
  };

  const loanPortfolioReport: LoanPortfolioReportResponse = {
    shg_id: mockGroup.id,
    shg_name: mockGroup.name,
    as_of_date: '2026-03-01',
    active_loans_count: 1,
    total_disbursed_principal: '25000.00',
    total_outstanding_principal: '20000.00',
    total_overdue_principal: '0.00',
    par_30: '0.0',
    par_60: '0.0',
    par_90: '0.0',
    aging_buckets: [],
    loans: [
      {
        loan_id: 'l1',
        loan_number: 'LN-2026-001',
        borrower_name: 'Radha Devi',
        principal: '25000.00',
        outstanding_principal: '20000.00',
        overdue_principal: '0.00',
        days_overdue: 0,
        aging_bucket: 'Current',
        status: 'ACTIVE',
      },
    ],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'admin@shg.org',
        role: 'ADMIN',
        is_active: true,
        group_access: [],
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        failed_login_count: 0,
      },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
      hasRole: () => true,
      hasGroupAccess: () => true,
    });

    vi.spyOn(apiClient.groups, 'list').mockResolvedValue({
      items: [mockGroup as any],
      total: 1,
      page: 1,
      page_size: 20,
    });

    vi.spyOn(apiClient.members, 'listByGroup').mockResolvedValue({
      items: [
        {
          id: 'm1',
          shg_id: mockGroup.id,
          full_name: 'Radha Devi',
          phone: '9876543210',
          address: 'Village Rampur',
          id_proof_type: 'Aadhaar',
          id_proof_last4: '1234',
          joined_on: '2025-01-01',
          status: 'ACTIVE',
        } as any,
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    vi.spyOn(apiClient.reports, 'getGroupDashboard').mockResolvedValue(groupDashboardReport);
    vi.spyOn(apiClient.reports, 'getGroupLedger').mockResolvedValue(groupLedgerReport);
    vi.spyOn(apiClient.reports, 'getLoanPortfolio').mockResolvedValue(loanPortfolioReport);
  });

  it('renders reports filter bar and preview for Group Dashboard', async () => {
    render(
      <BrowserRouter>
        <ReportsPage />
      </BrowserRouter>
    );

    expect(screen.getByText('Reports & Financial Statements')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Total Corpus')).toBeInTheDocument();
      expect(screen.getByText('₹50,000.00')).toBeInTheDocument();
      expect(screen.getByText('Radha Devi')).toBeInTheDocument();
    });
  });

  it('switches to Group Ledger & Trial Balance with double-entry balanced assertion', async () => {
    render(
      <BrowserRouter>
        <ReportsPage />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Total Corpus')).toBeInTheDocument();
    });

    // Select Group Ledger
    const reportTypeSelect = screen.getByLabelText(/Report Type/i);
    await userEvent.selectOptions(reportTypeSelect, 'group-ledger');

    await waitFor(() => {
      expect(screen.getByText('Trial Balance')).toBeInTheDocument();
      expect(screen.getByText('Balanced Double-Entry')).toBeInTheDocument();
      expect(screen.getByText('Cash in Hand')).toBeInTheDocument();
      expect(screen.getByText('Group Corpus Capital')).toBeInTheDocument();
    });
  });

  it('switches to Loan Portfolio and renders registry', async () => {
    render(
      <BrowserRouter>
        <ReportsPage />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Total Corpus')).toBeInTheDocument();
    });

    const reportTypeSelect = screen.getByLabelText(/Report Type/i);
    await userEvent.selectOptions(reportTypeSelect, 'loan-portfolio');

    await waitFor(() => {
      expect(screen.getByText('Loan Portfolio Registry')).toBeInTheDocument();
      expect(screen.getByText('LN-2026-001')).toBeInTheDocument();
      expect(screen.getByText('Total Disbursed')).toBeInTheDocument();
    });
  });

  it('triggers CSV export download on button click', async () => {
    const mockBlob = new Blob(['sample,csv,data'], { type: 'text/csv' });
    const exportSpy = vi.spyOn(apiClient.reports, 'exportGroupDashboardCsv').mockResolvedValue(mockBlob);

    // Mock window.URL and anchor click to prevent jsdom navigation error
    window.URL.createObjectURL = vi.fn().mockReturnValue('blob:http://localhost/test');
    window.URL.revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    render(
      <BrowserRouter>
        <ReportsPage />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Export to CSV')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Export to CSV'));

    await waitFor(() => {
      expect(exportSpy).toHaveBeenCalledWith(mockGroup.id);
      expect(window.URL.createObjectURL).toHaveBeenCalled();
      expect(clickSpy).toHaveBeenCalled();
    });
  });
});
