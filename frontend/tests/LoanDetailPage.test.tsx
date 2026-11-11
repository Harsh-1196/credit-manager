import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LoanDetailPage } from '../src/features/loans/LoanDetailPage';
import { api } from '../src/lib/api/client';
import { AuthContext } from '../src/lib/auth/AuthContext';
import type { LoanDetailResponse, LoanStatusHistoryResponse, LoanDisbursePreviewResponse, LoanRepayPreviewResponse } from '../src/lib/api/types';

const mockHistory: LoanStatusHistoryResponse[] = [
  {
    id: 'h-1',
    loan_id: 'loan-12345678-0000-0000-0000-000000000001',
    from_status: 'DRAFT',
    to_status: 'SUBMITTED',
    actor_id: 'user-leader-1',
    reason: 'Initial application submitted',
    created_at: '2026-01-01T10:00:00Z',
  },
  {
    id: 'h-2',
    loan_id: 'loan-12345678-0000-0000-0000-000000000001',
    from_status: 'SUBMITTED',
    to_status: 'APPROVED',
    actor_id: 'user-admin-1',
    reason: 'Approved after verification',
    created_at: '2026-01-02T10:00:00Z',
  },
  {
    id: 'h-3',
    loan_id: 'loan-12345678-0000-0000-0000-000000000001',
    from_status: 'APPROVED',
    to_status: 'ACTIVE',
    actor_id: 'user-leader-1',
    reason: 'Disbursed to member',
    created_at: '2026-01-03T10:00:00Z',
  },
];

const mockLoanDetail: LoanDetailResponse = {
  id: 'loan-12345678-0000-0000-0000-000000000001',
  shg_id: 'group-11111111-0000-0000-0000-000000000001',
  member_id: 'member-22222222-0000-0000-0000-000000000001',
  member_name: 'Radha Devi',
  loan_number: 'LN-2026-0001',
  purpose: 'Livestock purchase',
  principal: '10000.00',
  interest_rate: '12.000',
  interest_type: 'REDUCING',
  tenure_months: 5,
  processing_fee: '100.00',
  status: 'ACTIVE',
  applied_by: 'user-leader-1',
  applied_at: '2026-01-01T10:00:00Z',
  approved_by: 'user-admin-1',
  approved_at: '2026-01-02T10:00:00Z',
  disbursed_at: '2026-01-03T10:00:00Z',
  disbursed_by: 'user-leader-1',
  first_due_date: '2026-02-01',
  closed_at: null,
  version: 3,
  created_at: '2026-01-01T10:00:00Z',
  can_approve: false,
  history: mockHistory,
  schedule: [
    {
      installment_no: 1,
      due_date: '2026-02-01',
      principal_due: '1960.36',
      interest_due: '100.00',
      total_due: '2060.36',
      outstanding_balance: '0.00',
      principal_paid: '1960.36',
      interest_paid: '100.00',
      penalty_paid: '0.00',
      penalty_due: '0.00',
      status: 'PAID',
      days_overdue: 0,
    },
    {
      installment_no: 2,
      due_date: '2026-03-01',
      principal_due: '1979.97',
      interest_due: '80.39',
      total_due: '2060.36',
      outstanding_balance: '1979.97',
      principal_paid: '0.00',
      interest_paid: '0.00',
      penalty_paid: '0.00',
      penalty_due: '25.00',
      status: 'OVERDUE',
      days_overdue: 14,
    },
  ],
  summary: {
    outstanding_principal: '8039.64',
    outstanding_interest: '320.50',
    outstanding_penalty: '25.00',
    total_outstanding_balance: '8385.14',
    total_principal_paid: '1960.36',
    total_interest_paid: '100.00',
    total_penalty_paid: '0.00',
    next_due_date: '2026-03-01',
    next_due_amount: '2085.36',
    days_overdue: 14,
  },
};

const mockDisbursePreview: LoanDisbursePreviewResponse = {
  loan_id: 'loan-12345678-0000-0000-0000-000000000001',
  loan_number: 'LN-2026-0001',
  member_name: 'Radha Devi',
  principal: '10000.00',
  processing_fee: '100.00',
  net_disbursed: '9900.00',
  group_cash_balance: '50000.00',
  has_sufficient_cash: true,
  journal_lines: [
    {
      account_code: '1100-radha',
      account_name: 'Member Loans Receivable - Radha Devi',
      debit: '10000.00',
      credit: '0.00',
    },
    {
      account_code: '1000',
      account_name: 'Cash in Hand',
      debit: '0.00',
      credit: '9900.00',
    },
    {
      account_code: '4020',
      account_name: 'Processing Fee Income',
      debit: '0.00',
      credit: '100.00',
    },
  ],
};

const mockRepayPreview: LoanRepayPreviewResponse = {
  loan_id: 'loan-12345678-0000-0000-0000-000000000001',
  loan_number: 'LN-2026-0001',
  payment_amount: '2500.00',
  penalty_allocated: '25.00',
  interest_allocated: '80.39',
  principal_allocated: '1979.97',
  prepayment_principal: '414.64',
  is_loan_fully_paid: false,
  remaining_principal_after: '5645.03',
  installments_affected: [],
};

const mockAuthValue = {
  user: {
    id: 'user-admin-1',
    email: 'admin@shg.org',
    role: 'ADMIN' as const,
    is_active: true,
    failed_login_count: 0,
    created_at: '2026-01-01',
    updated_at: '2026-01-01',
    group_access: [{ group_id: 'group-11111111-0000-0000-0000-000000000001', group_name: 'Ekta', access_level: 'ADMIN' }],
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

describe('Screen 8: Loan Detail Page', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    queryClient.clear();
    vi.spyOn(api.loans, 'get').mockResolvedValue(mockLoanDetail);
    vi.spyOn(api.loans, 'history').mockResolvedValue(mockHistory);
    vi.spyOn(api.loans, 'getDisbursePreview').mockResolvedValue(mockDisbursePreview);
    vi.spyOn(api.loans, 'previewRepayment').mockResolvedValue(mockRepayPreview);
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={mockAuthValue}>
          <MemoryRouter initialEntries={['/loans/loan-12345678-0000-0000-0000-000000000001']}>
            <Routes>
              <Route path="/loans/:id" element={<LoanDetailPage />} />
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>
    );

  it('renders Screen 8 3-column layout: timeline (left), schedule table (center), summary balances (right)', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('LN-2026-0001')).toBeInTheDocument();
    });

    // 1. Left column: Status Timeline
    expect(screen.getByText(/Status Timeline/i)).toBeInTheDocument();
    expect(screen.getAllByText(/SUBMITTED/i).length).toBeGreaterThan(0);

    // 2. Center column: Schedule table
    expect(screen.getByText(/Repayment Schedule/i)).toBeInTheDocument();
    expect(screen.getAllByText(/1,960\.36/)[0]).toBeInTheDocument();

    // 3. Right column: Summary balances
    expect(screen.getByText(/Loan Balances/i)).toBeInTheDocument();
    expect(screen.getByText(/8,039\.64/)).toBeInTheDocument();
    expect(screen.getByText(/Available Actions/i)).toBeInTheDocument();
  });

  it('displays "Overdue N days" explicit text cue for past-due installments', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getAllByText(/Overdue 14 days/i).length).toBeGreaterThan(0);
    });
  });

  it('opens Disburse Dialog and renders restated figures and double-entry journal lines', async () => {
    vi.mocked(api.loans.get).mockResolvedValueOnce({
      ...mockLoanDetail,
      status: 'APPROVED',
      schedule: [],
    });

    renderComponent();

    const disburseBtns = await screen.findAllByRole('button', { name: /Disburse Loan/i });
    expect(disburseBtns.length).toBeGreaterThan(0);
    fireEvent.click(disburseBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/Disburse Loan & Confirm Journal Lines/i)).toBeInTheDocument();
      // Restated figures
      expect(screen.getAllByText(/9,900\.00/).length).toBeGreaterThan(0);
      expect(screen.getByText(/\[SUFFICIENT\]/i)).toBeInTheDocument();
      // Double entry journal lines
      expect(screen.getByText(/Member Loans Receivable - Radha Devi/i)).toBeInTheDocument();
      expect(screen.getAllByText(/Cash in Hand/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/Processing Fee Income/i)).toBeInTheDocument();
    });
  });

  it('opens Repayment Dialog and shows live allocation breakdown preview', async () => {
    renderComponent();

    const repayBtns = await screen.findAllByRole('button', { name: /Record Repayment/i });
    expect(repayBtns.length).toBeGreaterThan(0);
    fireEvent.click(repayBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/Record Loan Repayment/i)).toBeInTheDocument();
    });

    // Enter repayment amount
    const amountInput = screen.getByPlaceholderText(/2500.00/i);
    fireEvent.change(amountInput, { target: { value: '2500' } });

    await waitFor(() => {
      expect(screen.getByText(/Live Repayment Allocation/i)).toBeInTheDocument();
      expect(screen.getByText(/414\.64/)).toBeInTheDocument(); // Prepayment applied
      expect(screen.getByText(/5,645\.03/)).toBeInTheDocument(); // Principal balance after
    });
  });
});
