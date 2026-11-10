import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemberPassbookTab } from '../src/features/members/MemberPassbookTab';
import { AuthContext } from '../src/lib/auth/AuthContext';
import { api } from '../src/lib/api/client';

vi.mock('../src/lib/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api/client')>('../src/lib/api/client');
  return {
    ...actual,
    api: {
      ledger: {
        getMemberPassbook: vi.fn(),
        reverseEntry: vi.fn(),
      },
    },
  };
});

const mockPassbookData = {
  member_id: 'm123',
  member_name: 'Anita Devi',
  shg_id: 'g456',
  total_savings_balance: '1250.00',
  entries: [
    {
      id: 'e1',
      entry_id: 'je1',
      entry_date: '2025-01-10',
      particulars: 'Monthly savings deposit',
      debit: '',
      credit: '500.00',
      balance: '500.00',
      is_reversal: false,
      reverses_entry_id: null,
    },
    {
      id: 'e2',
      entry_id: 'je2',
      entry_date: '2025-02-10',
      particulars: 'Monthly savings deposit',
      debit: '',
      credit: '500.00',
      balance: '1000.00',
      is_reversal: false,
      reverses_entry_id: null,
    },
    {
      id: 'e3',
      entry_id: 'je3',
      entry_date: '2025-02-15',
      particulars: 'Partial emergency withdrawal',
      debit: '250.00',
      credit: '',
      balance: '750.00',
      is_reversal: false,
      reverses_entry_id: null,
    },
    {
      id: 'e4',
      entry_id: 'je4',
      entry_date: '2025-02-20',
      particulars: 'Reversal of entry je3: Wrong member debited',
      debit: '',
      credit: '250.00',
      balance: '1000.00',
      is_reversal: true,
      reverses_entry_id: 'je3',
    },
  ],
};

function renderWithProviders(ui: React.ReactElement, role: 'ADMIN' | 'GROUP_LEADER' | 'MEMBER' = 'ADMIN') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  const authValue = {
    user: {
      id: 'u1',
      email: 'admin@shg.org',
      role,
      phone: '9876543210',
      is_active: true,
      failed_login_count: 0,
      group_ids: ['g456'],
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
      group_access: [],
    } as any,
    isLoading: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    refreshProfile: vi.fn(),
    hasRole: (...roles: string[]) => roles.includes(role),
    hasGroupAccess: () => true,
  };

  return render(
    <AuthContext.Provider value={authValue}>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </AuthContext.Provider>
  );
}

describe('MemberPassbookTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.ledger.getMemberPassbook).mockResolvedValue(mockPassbookData as any);
  });

  it('renders ruled-ledger look with separate Debit, Credit, and Balance columns', async () => {
    renderWithProviders(<MemberPassbookTab memberId="m123" memberName="Anita Devi" shgId="g456" />);

    await waitFor(() => {
      expect(screen.getByText(/Anita Devi's Savings Ledger/i)).toBeInTheDocument();
    });

    // Check table headers
    expect(screen.getByRole('columnheader', { name: /date/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /particulars/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /debit/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /credit/i })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /balance/i })).toBeInTheDocument();

    // Check entries are rendered
    expect(screen.getAllByText('Monthly savings deposit').length).toBe(2);
    expect(screen.getByText('Partial emergency withdrawal')).toBeInTheDocument();

    // Check Reversal indicator badge
    expect(screen.getByText('REVERSAL')).toBeInTheDocument();
  });

  it('shows Reverse action button only for ADMIN role', async () => {
    // 1. Render as ADMIN
    const { unmount } = renderWithProviders(
      <MemberPassbookTab memberId="m123" memberName="Anita Devi" shgId="g456" />,
      'ADMIN'
    );

    await waitFor(() => {
      expect(screen.getByRole('columnheader', { name: /actions/i })).toBeInTheDocument();
    });

    const reverseButtons = screen.getAllByRole('button', { name: /reverse/i });
    expect(reverseButtons.length).toBeGreaterThan(0);

    unmount();

    // 2. Render as MEMBER
    renderWithProviders(
      <MemberPassbookTab memberId="m123" memberName="Anita Devi" shgId="g456" />,
      'MEMBER'
    );

    await waitFor(() => {
      expect(screen.queryByRole('columnheader', { name: /actions/i })).not.toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /reverse/i })).not.toBeInTheDocument();
  });

  it('filters passbook entries by date range', async () => {
    renderWithProviders(<MemberPassbookTab memberId="m123" memberName="Anita Devi" shgId="g456" />);

    await waitFor(() => {
      expect(screen.getByText(/Anita Devi's Savings Ledger/i)).toBeInTheDocument();
    });

    const fromInput = screen.getByLabelText(/from date/i);
    const toInput = screen.getByLabelText(/to date/i);
    const filterBtn = screen.getByRole('button', { name: /filter/i });

    fireEvent.change(fromInput, { target: { value: '2025-02-01' } });
    fireEvent.change(toInput, { target: { value: '2025-02-28' } });
    fireEvent.click(filterBtn);

    await waitFor(() => {
      expect(api.ledger.getMemberPassbook).toHaveBeenCalledWith('m123', '2025-02-01', '2025-02-28');
    });
  });
});
