import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthContext } from '../src/lib/auth/AuthContext';
import { ApprovalsQueuePage } from '../src/features/loans/ApprovalsQueuePage';
import { LoanDetailPage } from '../src/features/loans/LoanDetailPage';
import { api } from '../src/lib/api/client';
import type { LoanResponse, LoanDetailResponse, LoanDisbursePreviewResponse } from '../src/lib/api/types';

vi.mock('../src/lib/api/client', () => ({
  api: {
    groups: {
      list: vi.fn(),
    },
    loans: {
      list: vi.fn(),
      get: vi.fn(),
      history: vi.fn(),
      approve: vi.fn(),
      reject: vi.fn(),
      getDisbursePreview: vi.fn(),
      disburse: vi.fn(),
      previewRepayment: vi.fn(),
      repay: vi.fn(),
      writeOff: vi.fn(),
    },
  },
}));

describe('Critical Flow: Approve and Disburse a Loan', () => {
  let queryClient: QueryClient;

  const mockLoanItem: LoanResponse = {
    id: 'loan-flow-001',
    shg_id: 'shg-001',
    member_id: 'mem-001',
    member_name: 'Sunita Devi',
    loan_number: 'LN-2026-0042',
    principal: '25000.00',
    interest_rate: '12.000',
    interest_type: 'REDUCING',
    tenure_months: 12,
    processing_fee: '250.00',
    purpose: 'Poultry farm setup',
    status: 'SUBMITTED',
    applied_by: 'user-animator-01',
    applied_at: '2026-02-15T09:00:00Z',
    created_at: '2026-02-15T09:00:00Z',
    version: 1,
    can_approve: true,
  };

  const mockLoanDetailApproved: LoanDetailResponse = {
    ...mockLoanItem,
    status: 'APPROVED',
    version: 2,
    approved_by: 'user-admin-01',
    approved_at: '2026-02-16T09:00:00Z',
    disbursed_at: null,
    disbursed_by: null,
    first_due_date: '2026-03-15',
    closed_at: null,
    can_approve: true,
    history: [],
    schedule: [],
    summary: {
      outstanding_principal: '25000.00',
      outstanding_interest: '1661.28',
      outstanding_penalty: '0.00',
      total_outstanding_balance: '26661.28',
      total_principal_paid: '0.00',
      total_interest_paid: '0.00',
      total_penalty_paid: '0.00',
      next_due_date: null,
      next_due_amount: '0.00',
      days_overdue: 0,
    },
  };

  const mockLoanDetailActive: LoanDetailResponse = {
    ...mockLoanDetailApproved,
    status: 'ACTIVE',
    version: 3,
    disbursed_at: '2026-02-16T10:00:00Z',
  };

  const mockDisbursePreview: LoanDisbursePreviewResponse = {
    loan_id: 'loan-flow-001',
    loan_number: 'LN-2026-0042',
    member_name: 'Sunita Devi',
    principal: '25000.00',
    processing_fee: '250.00',
    net_disbursed: '24750.00',
    group_cash_balance: '60000.00',
    has_sufficient_cash: true,
    journal_lines: [
      {
        account_code: '1100-sunita',
        account_name: 'Member Loans Receivable - Sunita Devi',
        debit: '25000.00',
        credit: '0.00',
      },
      {
        account_code: '1000',
        account_name: 'Cash in Hand',
        debit: '0.00',
        credit: '24750.00',
      },
      {
        account_code: '4020',
        account_name: 'Processing Fee Income',
        debit: '0.00',
        credit: '250.00',
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });

    vi.mocked(api.groups.list).mockResolvedValue({
      items: [{ id: 'shg-001', name: 'Phool Mahila SHG' }],
      total: 1,
      page: 1,
      page_size: 100,
      total_pages: 1,
    } as any);
    vi.mocked(api.loans.list).mockResolvedValue([mockLoanItem]);
    vi.mocked(api.loans.get).mockResolvedValue(mockLoanDetailApproved);
    vi.mocked(api.loans.history).mockResolvedValue([]);
    vi.mocked(api.loans.approve).mockResolvedValue({
      ...mockLoanItem,
      status: 'APPROVED',
      version: 2,
    });
    vi.mocked(api.loans.getDisbursePreview).mockResolvedValue(mockDisbursePreview);
    vi.mocked(api.loans.disburse).mockResolvedValue(mockLoanDetailActive);
  });

  const mockAdminAuth = {
    user: {
      id: 'user-admin-01',
      email: 'admin@shg.org',
      role: 'ADMIN' as const,
      is_active: true,
      failed_login_count: 0,
      group_access: [{ group_id: 'shg-001', group_name: 'Phool Mahila SHG', access_level: 'ADMIN' }],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      last_login_at: null,
    },
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    refreshProfile: vi.fn(),
    hasRole: vi.fn(() => true),
    hasGroupAccess: vi.fn(() => true),
  };

  it('completes the entire approve and disburse workflow', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={mockAdminAuth}>
          <MemoryRouter initialEntries={['/loans/approvals']}>
            <Routes>
              <Route path="/loans/approvals" element={<ApprovalsQueuePage />} />
              <Route path="/loans/:id" element={<LoanDetailPage />} />
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>
    );

    // Step 1: Approvals Queue displays pending loan
    await waitFor(() => {
      expect(screen.getByText('LN-2026-0042')).toBeInTheDocument();
      expect(screen.getByText('Sunita Devi')).toBeInTheDocument();
    });

    // Step 2: Checker approves the loan application
    const approveBtn = screen.getByRole('button', { name: /^Approve$/i });
    expect(approveBtn).toBeInTheDocument();
    fireEvent.click(approveBtn);

    // Dialog opens
    await waitFor(() => {
      expect(screen.getByText(/Confirm Loan Approval/i)).toBeInTheDocument();
    });
    const confirmApproveBtn = screen.getByRole('button', { name: /Confirm Approval/i });
    fireEvent.click(confirmApproveBtn);

    await waitFor(() => {
      expect(api.loans.approve).toHaveBeenCalledWith('loan-flow-001', {
        version: 1,
      });
    });

    // Step 3: Navigate to Loan Detail page for disbursal
    cleanup();
    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={mockAdminAuth}>
          <MemoryRouter initialEntries={['/loans/loan-flow-001']}>
            <Routes>
              <Route path="/loans/:id" element={<LoanDetailPage />} />
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('LN-2026-0042')).toBeInTheDocument();
    });

    // Step 4: Click Disburse Loan button to open confirmation dialog
    const disburseBtns = await screen.findAllByRole('button', { name: /Disburse Loan/i });
    expect(disburseBtns.length).toBeGreaterThan(0);
    fireEvent.click(disburseBtns[0]);

    // Step 5: Disburse Dialog shows restated figures and double-entry lines
    await waitFor(() => {
      expect(screen.getByText(/Disburse Loan & Confirm Journal Lines/i)).toBeInTheDocument();
      expect(screen.getAllByText(/24,750\.00/).length).toBeGreaterThan(0);
      expect(screen.getByText(/\[SUFFICIENT\]/i)).toBeInTheDocument();
      expect(screen.getByText(/Member Loans Receivable - Sunita Devi/i)).toBeInTheDocument();
    });

    // Step 6: Confirm Disbursal
    const confirmDisburseBtn = screen.getByRole('button', { name: /Confirm & Disburse/i });
    fireEvent.click(confirmDisburseBtn);

    await waitFor(() => {
      expect(api.loans.disburse).toHaveBeenCalledWith(
        'loan-flow-001',
        expect.objectContaining({ version: 2 }),
        expect.any(String)
      );
    });
  });
});
