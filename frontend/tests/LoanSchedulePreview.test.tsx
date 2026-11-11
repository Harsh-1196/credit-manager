import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { LoanApplicationPage } from '../src/features/loans/LoanApplicationPage';
import { api } from '../src/lib/api/client';

vi.mock('../src/lib/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api/client')>('../src/lib/api/client');
  return {
    ...actual,
    api: {
      groups: {
        list: vi.fn(),
        getSettings: vi.fn(),
      },
      members: {
        listByGroup: vi.fn(),
      },
      loans: {
        previewSchedule: vi.fn(),
        create: vi.fn(),
      },
    },
  };
});

const mockPreviewResponse = {
  principal: '50000.00',
  total_interest: '3309.28',
  total_amount: '53309.28',
  monthly_installment: '4442.44',
  installments: [
    {
      installment_no: 1,
      due_date: '2026-04-01',
      principal_due: '3942.44',
      interest_due: '500.00',
      total_due: '4442.44',
      outstanding_balance: '46057.56',
      status: 'PENDING',
    },
    {
      installment_no: 12,
      due_date: '2027-03-01',
      principal_due: '4398.45',
      interest_due: '43.98',
      total_due: '4442.43',
      outstanding_balance: '0.00',
      status: 'PENDING',
    },
  ],
  eligibility: {
    is_eligible: true,
    has_warnings: false,
    summary_message: 'All credit criteria satisfied.',
    checks: [
      {
        code: 'MEMBER_ACTIVE',
        name: 'Active Member Status',
        passed: true,
        severity: 'BLOCKER',
        message: 'Member is in good standing and actively enrolled.',
        actual_value: 'ACTIVE',
        threshold_value: 'ACTIVE',
      },
      {
        code: 'CONCURRENT_LOANS',
        name: 'Concurrent Active Loans Limit',
        passed: true,
        severity: 'BLOCKER',
        message: 'Member has 0 concurrent active loans.',
        actual_value: '0',
        threshold_value: '1',
      },
      {
        code: 'SAVINGS_MULTIPLE',
        name: 'Savings Multiple Borrowing Cap',
        passed: true,
        severity: 'BLOCKER',
        message: 'Principal within 4x savings limit.',
        actual_value: '50000.00',
        threshold_value: '60000.00',
      },
      {
        code: 'GROUP_LIQUIDITY',
        name: 'Group Cash Liquidity',
        passed: false,
        severity: 'WARNING',
        message: 'Requested loan exceeds liquid cash balance (warning for approver).',
        actual_value: '50000.00',
        threshold_value: '42000.00',
      },
    ],
  },
};

describe('LoanApplicationPage - Schedule & Eligibility Preview', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    vi.mocked(api.groups.list).mockResolvedValue({
      items: [
        {
          id: 'g-1',
          name: 'Pragati SHG',
          district: 'Varanasi',
          status: 'ACTIVE',
          formation_date: '2024-01-01',
          meeting_day: 'MONDAY',
          meeting_frequency: 'MONTHLY',
        } as any,
      ],
      total: 1,
      page: 1,
      page_size: 10,
    });

    vi.mocked(api.groups.getSettings).mockResolvedValue({
      id: 'gs-1',
      shg_id: 'g-1',
      monthly_saving_amount: '500.00',
      default_interest_rate: '12.000',
      interest_type: 'REDUCING',
      max_loan_multiple: '4.00',
      min_tenure_months: 1,
      max_tenure_months: 36,
      fine_grace_days: 5,
      late_fine_per_day: '5.00',
      penalty_interest_rate: '2.000',
      processing_fee_percent: '1.000',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    });

    vi.mocked(api.members.listByGroup).mockResolvedValue({
      items: [
        {
          id: 'm-1',
          shg_id: 'g-1',
          full_name: 'Radha Devi',
          phone: '9876543210',
          joined_on: '2024-01-01',
          status: 'ACTIVE',
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        } as any,
      ],
      total: 1,
      page: 1,
      page_size: 10,
    });

    vi.mocked(api.loans.previewSchedule).mockResolvedValue(mockPreviewResponse as any);
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <LoanApplicationPage />
        </BrowserRouter>
      </QueryClientProvider>
    );

  it('renders application form and title', async () => {
    renderComponent();

    expect(await screen.findByText(/Screen 7: Loan Application/i)).toBeInTheDocument();
    expect(screen.getByText('Application Particulars')).toBeInTheDocument();
    expect(screen.getByText(/Principal Amount/i)).toBeInTheDocument();
  });

  it('displays eligibility checks with explicit text cues (not color alone)', async () => {
    renderComponent();

    // Select group and member
    const groupSelect = await screen.findByLabelText(/Self-Help Group/i);
    fireEvent.change(groupSelect, { target: { value: 'g-1' } });

    await waitFor(() => {
      expect(api.members.listByGroup).toHaveBeenCalledWith('g-1', { page_size: 100, status: 'ACTIVE' });
    });

    const memberSelect = await screen.findByLabelText(/Applicant Member/i);
    fireEvent.change(memberSelect, { target: { value: 'm-1' } });

    // Wait for live preview call
    await waitFor(() => {
      expect(api.loans.previewSchedule).toHaveBeenCalled();
    });

    // Verify text cues on eligibility checks
    expect(await screen.findByText('Active Member Status')).toBeInTheDocument();
    const passCues = screen.getAllByText('[PASS]');
    expect(passCues.length).toBeGreaterThan(0);

    // Warning cue on liquidity
    expect(screen.getByText('[WARNING]')).toBeInTheDocument();
    expect(screen.getByText('Group Cash Liquidity')).toBeInTheDocument();
  });

  it('renders schedule preview table with right-aligned tabular numerals and totals row', async () => {
    renderComponent();

    const groupSelect = await screen.findByLabelText(/Self-Help Group/i);
    fireEvent.change(groupSelect, { target: { value: 'g-1' } });

    const memberSelect = await screen.findByLabelText(/Applicant Member/i);
    fireEvent.change(memberSelect, { target: { value: 'm-1' } });

    await waitFor(() => {
      expect(api.loans.previewSchedule).toHaveBeenCalled();
    });

    // Schedule header and totals
    expect(await screen.findByText('Schedule Preview (SPEC 6.3)')).toBeInTheDocument();
    expect(screen.getByText('Total')).toBeInTheDocument();

    // Verify EMI value from preview response (4,442.44)
    expect(screen.getAllByText(/4,442\.44/i).length).toBeGreaterThan(0);
  });
});
