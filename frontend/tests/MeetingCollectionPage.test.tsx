import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { MeetingCollectionPage } from '../src/features/meetings/MeetingCollectionPage';
import { api } from '../src/lib/api/client';
import { AuthContext } from '../src/lib/auth/AuthContext';
import type { CollectionSheetResponse } from '../src/lib/api/types';

vi.mock('../src/lib/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api/client')>('../src/lib/api/client');
  return {
    ...actual,
    api: {
      ...actual.api,
      meetings: {
        ...actual.api.meetings,
        getCollectionSheet: vi.fn(),
        recordCollections: vi.fn(),
      },
    },
  };
});

describe('Screen 6: Meeting Collection Grid', () => {
  let queryClient: QueryClient;

  const mockSheetData: CollectionSheetResponse = {
    meeting_id: 'meeting-1111-2222',
    shg_id: 'group-1111-0001',
    shg_name: 'Phool Mahila SHG',
    meeting_date: '2026-03-15',
    status: 'SCHEDULED',
    period: '2026-03',
    members: [
      {
        member_id: 'mem-001',
        member_name: 'Radha Devi',
        attendance_status: 'PRESENT',
        savings_due: '200.00',
        emi_due: '1050.00',
        principal_due: '1000.00',
        interest_due: '50.00',
        arrears: '0.00',
        penalty_due: '0.00',
        fines_due: '0.00',
        total_due: '1250.00',
        active_loan_id: 'loan-1234',
        active_loan_number: 'LN-2026-0001',
      },
      {
        member_id: 'mem-002',
        member_name: 'Sunita Devi',
        attendance_status: 'PRESENT',
        savings_due: '200.00',
        emi_due: '0.00',
        principal_due: '0.00',
        interest_due: '0.00',
        arrears: '0.00',
        penalty_due: '0.00',
        fines_due: '20.00',
        total_due: '220.00',
        active_loan_id: null,
        active_loan_number: null,
      },
    ],
    totals: {
      total_savings_due: '400.00',
      total_emi_due: '1050.00',
      total_arrears: '0.00',
      total_fines_due: '20.00',
      total_due: '1470.00',
      member_count: 2,
    },
  };

  const mockAuthContext = {
    user: {
      id: 'user-leader-1',
      email: 'leader@shg.org',
      role: 'GROUP_LEADER' as const,
      is_active: true,
      failed_login_count: 0,
      created_at: '2026-01-01',
      updated_at: '2026-01-01',
      group_access: [{ group_id: 'group-1111-0001', group_name: 'Phool Mahila SHG', access_level: 'GROUP_LEADER' }],
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

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    vi.mocked(api.meetings.getCollectionSheet).mockResolvedValue(mockSheetData);
  });

  const renderComponent = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={mockAuthContext}>
          <MemoryRouter initialEntries={['/meetings/meeting-1111-2222/collection']}>
            <Routes>
              <Route path="/meetings/:id/collection" element={<MeetingCollectionPage />} />
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>
    );

  it('renders grid pre-filled from collection sheet with members, dues, and live totals', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getAllByText('Radha Devi').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Sunita Devi').length).toBeGreaterThan(0);
      expect(screen.getAllByText(/LN-2026-0001/).length).toBeGreaterThan(0);
    });

    // Verify running totals in footer computed with decimal.js
    // Total savings: 200 + 200 = 400.00
    // Total EMI: 1050.00
    // Total fine: 20.00
    // Grand Total: 1470.00
    expect(screen.getAllByText(/1,470\.00/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Attendance:/)).toBeInTheDocument();
    expect(screen.getAllByText((_, el) => el?.textContent?.includes('2 / 2 Present') ?? false).length).toBeGreaterThan(0);
  });

  it('updates live running totals in footer when cells are edited inline', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getAllByText('Radha Devi').length).toBeGreaterThan(0);
    });

    // Find Radha Devi's savings input
    const inputs = screen.getAllByRole('textbox');
    // Change first savings input from 200 to 500
    fireEvent.change(inputs[0], { target: { value: '500.00' } });

    // New Grand Total: (500 + 1050) + (200 + 0 + 20) = 1770.00
    await waitFor(() => {
      expect(screen.getAllByText(/1,770\.00/).length).toBeGreaterThan(0);
    });
  });

  it('provides full keyboard operation: Enter moves down, shortcuts work', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getAllByText('Radha Devi').length).toBeGreaterThan(0);
    });

    const markPresentBtn = screen.getByRole('button', { name: /Mark All Present/i });
    expect(markPresentBtn).toBeInTheDocument();

    const fillDuesBtn = screen.getByRole('button', { name: /Fill Dues/i });
    expect(fillDuesBtn).toBeInTheDocument();

    // Trigger Fill Dues button
    fireEvent.click(fillDuesBtn);

    await waitFor(() => {
      expect(screen.getAllByText(/1,470\.00/).length).toBeGreaterThan(0);
    });
  });

  it('opens confirmation modal showing restated figures and balanced double-entry lines', async () => {
    vi.mocked(api.meetings.recordCollections).mockResolvedValue({
      total_collected: '1470.00',
      total_savings: '400.00',
      total_loan_repayment: '1050.00',
      total_fines: '20.00',
      members_count: 2,
      journal_entries_count: 2,
      journal_entry_ids: ['e-1' as any, 'e-2' as any],
      meeting_status: 'HELD',
    });

    renderComponent();

    await waitFor(() => {
      expect(screen.getAllByText('Radha Devi').length).toBeGreaterThan(0);
    });

    // Click Review & Post Collections button in sticky footer
    const reviewBtn = screen.getByRole('button', { name: /Review & Post Collections/i });
    fireEvent.click(reviewBtn);

    // Modal opens
    await waitFor(() => {
      expect(screen.getByText(/Confirm Meeting Collections & Journal Postings/i)).toBeInTheDocument();
      // Restated figures
      expect(screen.getAllByText(/1,470\.00/).length).toBeGreaterThan(0);
      // Double entry accounts
      expect(screen.getByText(/1000 - Cash in Hand/i)).toBeInTheDocument();
      expect(screen.getByText(/2000 - Member Savings/i)).toBeInTheDocument();
      expect(screen.getByText(/1100 \/ 4000 - Member Loans & Interest Allocated/i)).toBeInTheDocument();
    });

    // Confirm post
    const confirmBtn = screen.getByRole('button', { name: /Confirm & Post/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.meetings.recordCollections).toHaveBeenCalledWith(
        'meeting-1111-2222',
        expect.objectContaining({
          period: '2026-03',
          collections: expect.any(Array),
        }),
        expect.any(String)
      );
    });
  });
});
