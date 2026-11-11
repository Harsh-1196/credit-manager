import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ApprovalsQueuePage } from '../src/features/loans/ApprovalsQueuePage';
import { api } from '../src/lib/api/client';

vi.mock('../src/lib/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api/client')>('../src/lib/api/client');
  return {
    ...actual,
    api: {
      groups: {
        list: vi.fn(),
      },
      loans: {
        list: vi.fn(),
        approve: vi.fn(),
        reject: vi.fn(),
      },
    },
  };
});

const mockLoans = [
  {
    id: 'loan-1',
    shg_id: 'group-1',
    member_id: 'member-1',
    member_name: 'Radha Devi',
    loan_number: 'LN-PRAGATI-001',
    principal: '25000.00',
    interest_rate: '12.00',
    interest_type: 'REDUCING',
    tenure_months: 12,
    processing_fee: '250.00',
    purpose: 'Livestock purchase',
    status: 'SUBMITTED',
    applied_by: 'user-leader',
    applied_at: '2026-03-01T10:00:00Z',
    version: 2,
    can_approve: false,
    maker_checker_note:
      'Maker-checker restriction: You created this loan application and cannot approve it. Another leader or admin must approve.',
  },
  {
    id: 'loan-2',
    shg_id: 'group-1',
    member_id: 'member-2',
    member_name: 'Sunita Sharma',
    loan_number: 'LN-PRAGATI-002',
    principal: '10000.00',
    interest_rate: '12.00',
    interest_type: 'REDUCING',
    tenure_months: 6,
    processing_fee: '100.00',
    purpose: 'Agriculture fertilizer',
    status: 'SUBMITTED',
    applied_by: 'user-member-2',
    applied_at: '2026-03-02T11:00:00Z',
    version: 2,
    can_approve: true,
    maker_checker_note: null,
  },
];

describe('ApprovalsQueuePage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    vi.mocked(api.groups.list).mockResolvedValue({
      items: [{ id: 'group-1', name: 'Pragati SHG', district: 'Varanasi', status: 'ACTIVE', formation_date: '2024-01-01', meeting_day: 'MONDAY', meeting_frequency: 'MONTHLY' } as any],
      total: 1,
      page: 1,
      page_size: 10,
    });

    vi.mocked(api.loans.list).mockResolvedValue(mockLoans as any);
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ApprovalsQueuePage />
        </BrowserRouter>
      </QueryClientProvider>
    );

  it('renders pending loan applications in queue', async () => {
    renderComponent();

    expect(await screen.findByText('LN-PRAGATI-001')).toBeInTheDocument();
    expect(screen.getByText('Radha Devi')).toBeInTheDocument();
    expect(screen.getByText('LN-PRAGATI-002')).toBeInTheDocument();
    expect(screen.getByText('Sunita Sharma')).toBeInTheDocument();
  });

  it('enforces maker-checker rule: creator has disabled approve button with explanation note', async () => {
    renderComponent();

    expect(await screen.findByText('LN-PRAGATI-001')).toBeInTheDocument();

    // Verify maker-checker note is displayed on screen
    expect(
      screen.getByText(/Maker-checker restriction: You created this loan application and cannot approve it/i)
    ).toBeInTheDocument();

    // Get all approve buttons
    const approveButtons = screen.getAllByRole('button', { name: /approve/i });
    expect(approveButtons.length).toBe(2);

    // The first one (loan-1 where can_approve=false) must be disabled
    expect(approveButtons[0]).toBeDisabled();

    // The second one (loan-2 where can_approve=true) must be enabled
    expect(approveButtons[1]).not.toBeDisabled();
  });

  it('allows approving permitted loan and submits with expected version', async () => {
    vi.mocked(api.loans.approve).mockResolvedValue({
      ...mockLoans[1],
      status: 'APPROVED',
      version: 3,
    } as any);

    renderComponent();

    expect(await screen.findByText('LN-PRAGATI-002')).toBeInTheDocument();

    const approveButtons = screen.getAllByRole('button', { name: /approve/i });
    // Click the active Approve button for loan-2
    fireEvent.click(approveButtons[1]);

    // Confirmation dialog opens
    expect(await screen.findByText('Confirm Loan Approval')).toBeInTheDocument();
    expect(screen.getByText('Confirm Approval')).toBeInTheDocument();

    // Confirm approval
    fireEvent.click(screen.getByText('Confirm Approval'));

    await waitFor(() => {
      expect(api.loans.approve).toHaveBeenCalledWith('loan-2', { version: 2 });
    });
  });

  it('reject button requires non-empty explanation reason', async () => {
    renderComponent();

    expect(await screen.findByText('LN-PRAGATI-001')).toBeInTheDocument();

    const rejectButtons = screen.getAllByRole('button', { name: /reject/i });
    fireEvent.click(rejectButtons[0]);

    // Reject dialog opens
    expect(await screen.findByText('Reject Loan Application')).toBeInTheDocument();

    // Try submitting without reason
    const submitRejectBtn = screen.getByRole('button', { name: 'Reject Application' });
    fireEvent.click(submitRejectBtn);

    // Shows validation error
    expect(
      await screen.findByText('A clear explanation of at least 3 characters is required.')
    ).toBeInTheDocument();
    expect(api.loans.reject).not.toHaveBeenCalled();

    // Type valid reason and submit
    vi.mocked(api.loans.reject).mockResolvedValue({
      ...mockLoans[0],
      status: 'REJECTED',
      version: 3,
    } as any);

    const input = screen.getByPlaceholderText(/Insufficient group liquidity/i);
    fireEvent.change(input, { target: { value: 'Incomplete KYC documentation' } });
    fireEvent.click(submitRejectBtn);

    await waitFor(() => {
      expect(api.loans.reject).toHaveBeenCalledWith('loan-1', {
        version: 2,
        reason: 'Incomplete KYC documentation',
      });
    });
  });
});
