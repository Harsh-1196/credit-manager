import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { MeetingCollectionPage } from '../src/features/meetings/MeetingCollectionPage';
import { MemberPassbookTab } from '../src/features/members/MemberPassbookTab';
import { api } from '../src/lib/api/client';
import { AuthContext } from '../src/lib/auth/AuthContext';
import type {
  CollectionSheetResponse,
  MeetingBatchCollectionsResponse,
} from '../src/lib/api/types';

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
      ledger: {
        ...actual.api.ledger,
        getMemberPassbook: vi.fn(),
      },
    },
  };
});

describe('Critical Flow: Record Meeting Collection & Verify Passbook Updated', () => {
  let queryClient: QueryClient;

  const mockSheetData: CollectionSheetResponse = {
    meeting_id: 'meeting-flow-001',
    shg_id: 'group-flow-001',
    shg_name: 'Kashi Mahila SHG',
    meeting_date: '2026-03-20',
    status: 'SCHEDULED',
    period: '2026-03',
    members: [
      {
        member_id: 'mem-flow-001',
        member_name: 'Anandi Devi',
        attendance_status: 'PRESENT',
        savings_due: '200.00',
        emi_due: '1200.00',
        principal_due: '1100.00',
        interest_due: '100.00',
        arrears: '0.00',
        penalty_due: '0.00',
        fines_due: '0.00',
        total_due: '1400.00',
        active_loan_id: 'loan-flow-001',
        active_loan_number: 'LN-2026-0099',
      },
    ],
    totals: {
      total_savings_due: '200.00',
      total_emi_due: '1200.00',
      total_arrears: '0.00',
      total_fines_due: '0.00',
      total_due: '1400.00',
      member_count: 1,
    },
  };

  const mockBatchSuccessResponse: MeetingBatchCollectionsResponse = {
    total_collected: '1400.00',
    total_savings: '200.00',
    total_loan_repayment: '1200.00',
    total_fines: '0.00',
    members_count: 1,
    journal_entries_count: 1,
    journal_entry_ids: ['entry-flow-001' as any],
    meeting_status: 'HELD',
  };

  const mockPassbookAfterCollection: any = {
    member_id: 'mem-flow-001',
    member_name: 'Anandi Devi',
    shg_id: 'group-flow-001',
    from_date: null,
    to_date: null,
    total_savings_balance: '200.00',
    closing_balance: '200.00',
    entries: [
      {
        id: 'entry-flow-001',
        entry_id: 'entry-flow-001',
        entry_date: '2026-03-20',
        particulars: 'Meeting collection - Anandi Devi (Savings: ₹200.00, EMI: ₹1200.00, Fine: ₹0.00)',
        description: 'Meeting collection - Anandi Devi (Savings: ₹200.00, EMI: ₹1200.00, Fine: ₹0.00)',
        source_type: 'SAVINGS',
        source_id: 'meeting-flow-001',
        debit: '0.00',
        credit: '200.00',
        balance: '200.00',
        running_balance: '200.00',
        can_reverse: true,
      },
    ],
  };

  const mockLeaderAuth = {
    user: {
      id: 'user-leader-01',
      email: 'leader@shg.org',
      role: 'GROUP_LEADER' as const,
      is_active: true,
      failed_login_count: 0,
      created_at: '2026-01-01',
      updated_at: '2026-01-01',
      group_access: [{ group_id: 'group-flow-001', group_name: 'Kashi Mahila SHG', access_level: 'GROUP_LEADER' }],
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
    vi.mocked(api.meetings.recordCollections).mockResolvedValue(mockBatchSuccessResponse);
    vi.mocked(api.ledger.getMemberPassbook).mockResolvedValue(mockPassbookAfterCollection);
  });

  it('completes the full meeting collection flow and verifies member passbook reflects updated ledger entry', async () => {
    // Step 1: Leader opens Meeting Collections Grid
    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={mockLeaderAuth}>
          <MemoryRouter initialEntries={['/meetings/meeting-flow-001/collection']}>
            <Routes>
              <Route path="/meetings/:id/collection" element={<MeetingCollectionPage />} />
            </Routes>
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>
    );

    // Step 2: Screen pre-fills member and dues
    await waitFor(() => {
      expect(screen.getAllByText('Anandi Devi').length).toBeGreaterThan(0);
      expect(screen.getAllByText(/LN-2026-0099/).length).toBeGreaterThan(0);
    });

    // Step 3: Check live sticky footer totals
    expect(screen.getAllByText(/1,400\.00/).length).toBeGreaterThan(0);

    // Step 4: Open review confirmation dialog
    const reviewBtn = screen.getByRole('button', { name: /Review & Post Collections/i });
    fireEvent.click(reviewBtn);

    await waitFor(() => {
      expect(screen.getByText(/Confirm Meeting Collections & Journal Postings/i)).toBeInTheDocument();
      expect(screen.getByText(/1000 - Cash in Hand/i)).toBeInTheDocument();
      expect(screen.getByText(/2000 - Member Savings/i)).toBeInTheDocument();
    });

    // Step 5: Confirm posting
    const confirmBtn = screen.getByRole('button', { name: /Confirm & Post/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.meetings.recordCollections).toHaveBeenCalledWith(
        'meeting-flow-001',
        expect.objectContaining({
          period: '2026-03',
          collections: expect.arrayContaining([
            expect.objectContaining({
              member_id: 'mem-flow-001',
              savings_amount: '200.00',
              loan_repayment_amount: '1200.00',
            }),
          ]),
        }),
        expect.any(String) // Idempotency key
      );
    });

    // Success banner displayed
    await waitFor(() => {
      expect(screen.getByText(/Meeting Collections Posted:/i)).toBeInTheDocument();
    });

    // Step 6: Navigate to Member Passbook and verify updated credit entry
    cleanup();

    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider value={mockLeaderAuth}>
          <MemberPassbookTab
            memberId="mem-flow-001"
            memberName="Anandi Devi"
            shgId="group-flow-001"
          />
        </AuthContext.Provider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText(/Savings Ledger/i)).toBeInTheDocument();
      expect(screen.getByText(/Meeting collection - Anandi Devi/i)).toBeInTheDocument();
      expect(screen.getAllByText(/200\.00/).length).toBeGreaterThan(0);
    });
  });
});
