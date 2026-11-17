import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { DashboardPage } from '../src/features/dashboard/DashboardPage';
import { apiClient } from '../src/lib/api/client';
import * as AuthContextModule from '../src/lib/auth/AuthContext';
import type { DashboardResponse, UserRole } from '../src/lib/api/types';

// Mock recharts responsive container for jsdom
vi.mock('recharts', async (importOriginal) => {
  const original = await importOriginal<Record<string, any>>();
  return {
    ...original,
    ResponsiveContainer: ({ children }: any) => (
      <div style={{ width: '800px', height: '300px' }}>{children}</div>
    ),
  };
});

describe('Screen 2: Dashboard & Role-Aware Views', () => {
  const mockAuthForRole = (role: UserRole) => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        email: `${role.toLowerCase()}@shg.org`,
        phone: '9876543210',
        role,
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
      hasRole: (...roles: UserRole[]) => roles.includes(role),
      hasGroupAccess: () => true,
    });
  };

  const adminDashboardData: DashboardResponse = {
    role: 'ADMIN',
    group_dashboard: {
      shg_id: 'g0000000-0000-0000-0000-000000000001',
      shg_name: 'Udaan Mahila Mandal',
      as_of_date: '2026-03-01',
      figures: {
        total_corpus: '120000.00',
        total_savings: '45000.00',
        outstanding_principal: '85000.00',
        interest_earned: '5400.00',
        repayment_rate: '96.8',
        overdue_amount: '12500.00',
        next_meeting_date: '2026-03-10',
        collections_due_next_meeting: '7500.00',
      },
      collections_due: [
        {
          member_id: 'm0000000-0000-0000-0000-000000000001',
          member_name: 'Radha Devi',
          savings_due: '500.00',
          emi_due: '1100.00',
          arrears: '0.00',
          fines: '0.00',
          total_due: '1600.00',
        },
        {
          member_id: 'm0000000-0000-0000-0000-000000000002',
          member_name: 'Sunita Kumari',
          savings_due: '500.00',
          emi_due: '0.00',
          arrears: '500.00',
          fines: '25.00',
          total_due: '1025.00',
        },
      ],
      aging_buckets: [
        { bucket: 'Current', count: 8, amount: '65000.00' },
        { bucket: '1-30 Days', count: 1, amount: '10000.00' },
        { bucket: '31-60 Days', count: 1, amount: '10000.00' },
        { bucket: '61-90 Days', count: 0, amount: '0.00' },
        { bucket: '90+ Days', count: 0, amount: '0.00' },
      ],
      savings_trend: [
        { month: '2025-10', amount: '15000.00' },
        { month: '2025-11', amount: '22000.00' },
        { month: '2025-12', amount: '30000.00' },
        { month: '2026-01', amount: '38000.00' },
        { month: '2026-02', amount: '45000.00' },
      ],
      disbursals_vs_repayments: [
        { month: '2025-11', disbursed: '30000.00', repaid: '8000.00' },
        { month: '2025-12', disbursed: '20000.00', repaid: '12000.00' },
        { month: '2026-01', disbursed: '15000.00', repaid: '14000.00' },
        { month: '2026-02', disbursed: '25000.00', repaid: '16000.00' },
      ],
    },
    member_dashboard: null,
  };

  const memberDashboardData: DashboardResponse = {
    role: 'MEMBER',
    group_dashboard: null,
    member_dashboard: {
      member: {
        member_id: 'm0000000-0000-0000-0000-000000000001',
        name: 'Radha Devi',
        phone: '9876543210',
        shg_name: 'Udaan Mahila Mandal',
        status: 'ACTIVE',
        join_date: '2025-01-01',
        total_savings_balance: '12500.00',
        total_loans_taken: 1,
        current_outstanding_principal: '8000.00',
        attendance_rate: '100.0',
      },
      passbook_entries: [
        {
          entry_id: 'e0000000-0000-0000-0000-000000000001',
          date: '2026-02-10',
          particulars: 'Monthly Savings Deposit',
          source_type: 'SAVINGS',
          debit: '0.00',
          credit: '500.00',
          balance: '12500.00',
        },
      ],
      active_loans: [
        {
          loan_id: 'l0000000-0000-0000-0000-000000000001',
          loan_number: 'LN-2026-001',
          principal: '10000.00',
          outstanding_principal: '8000.00',
          interest_rate: '12.0',
          status: 'ACTIVE',
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
          member_count: 10,
        } as any,
      ],
      attendance_summary: {
        total_meetings: 12,
        present: 12,
        absent: 0,
        percentage: 100.0,
      },
    },
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient.groups, 'list').mockResolvedValue({
      items: [
        {
          id: 'g0000000-0000-0000-0000-000000000001',
          name: 'Udaan Mahila Mandal',
          village: 'Rampur',
          district: 'Varanasi',
          formation_date: '2025-01-01',
          meeting_day: 'MONDAY',
          meeting_frequency: 'MONTHLY',
          status: 'ACTIVE',
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
          member_count: 10,
        } as any,
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
  });

  it('renders ADMIN Group Dashboard with abbreviated key figures and tooltips with full amounts', async () => {
    mockAuthForRole('ADMIN');
    vi.spyOn(apiClient.dashboard, 'get').mockResolvedValue(adminDashboardData);

    render(
      <BrowserRouter>
        <DashboardPage />
      </BrowserRouter>
    );

    // Group Title
    await waitFor(() => {
      expect(screen.getByText('Udaan Mahila Mandal')).toBeInTheDocument();
    });

    // Key figures in serif face with abbreviations
    // 120,000 -> 1.2L
    const corpusElements = screen.getAllByText('₹1.2L');
    expect(corpusElements.length).toBeGreaterThan(0);
    // Tooltip should contain full amount ₹1,20,000.00
    expect(corpusElements[0]).toHaveAttribute('title', 'Full Corpus: ₹1,20,000.00');

    // 85,000 -> 85K
    const outstandingElements = screen.getAllByText('₹85K');
    expect(outstandingElements.length).toBeGreaterThan(0);
    expect(outstandingElements[0]).toHaveAttribute('title', 'Full Outstanding: ₹85,000.00');

    // Repayment rate 96.8%
    expect(screen.getByText('96.8%')).toBeInTheDocument();

    // 12,500 -> 12.5K
    const overdueElements = screen.getAllByText('₹12.5K');
    expect(overdueElements.length).toBeGreaterThan(0);
    expect(overdueElements[0]).toHaveAttribute('title', 'Full Overdue: ₹12,500.00');

    // Collections due list
    expect(screen.getByText('Upcoming Collections Due')).toBeInTheDocument();
    expect(screen.getByText('Radha Devi')).toBeInTheDocument();
    expect(screen.getByText('Sunita Kumari')).toBeInTheDocument();
  });

  it('toggles accessible data table alternative for charts', async () => {
    mockAuthForRole('ADMIN');
    vi.spyOn(apiClient.dashboard, 'get').mockResolvedValue(adminDashboardData);

    render(
      <BrowserRouter>
        <DashboardPage />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Udaan Mahila Mandal')).toBeInTheDocument();
    });

    // Find table toggle buttons
    const tableButtons = screen.getAllByLabelText('View as Accessible Table');
    expect(tableButtons.length).toBeGreaterThan(0);

    // Click table toggle for savings trend
    await userEvent.click(tableButtons[0]);

    // Tabular header should now appear
    expect(screen.getByText('Period (Month)')).toBeInTheDocument();
    expect(screen.getByText('Cumulative Savings')).toBeInTheDocument();
    expect(screen.getByText('2025-10')).toBeInTheDocument();
  });

  it('renders role-aware MEMBER Dashboard with savings, loans, and passbook activity', async () => {
    mockAuthForRole('MEMBER');
    vi.spyOn(apiClient.dashboard, 'get').mockResolvedValue(memberDashboardData);

    render(
      <BrowserRouter>
        <DashboardPage />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Welcome, Radha Devi')).toBeInTheDocument();
    });

    // Member savings balance: 12,500 -> 12.5K
    expect(screen.getByText('₹12.5K')).toBeInTheDocument();
    // Loan outstanding: 8,000 -> 8K
    expect(screen.getByText('₹8K')).toBeInTheDocument();

    // Passbook recent activity
    expect(screen.getByText('Recent Passbook Activity')).toBeInTheDocument();
    expect(screen.getByText('Monthly Savings Deposit')).toBeInTheDocument();

    // Active loans
    expect(screen.getByText('My Active Loans')).toBeInTheDocument();
    expect(screen.getByText('LN-2026-001')).toBeInTheDocument();
  });
});
