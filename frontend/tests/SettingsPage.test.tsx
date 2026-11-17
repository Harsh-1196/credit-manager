import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { SettingsPage } from '../src/features/settings/SettingsPage';
import { apiClient } from '../src/lib/api/client';
import * as AuthContextModule from '../src/lib/auth/AuthContext';
import type { GroupResponse, GroupSettingsResponse, UserResponse } from '../src/lib/api/types';

describe('Screen 12: System & Group Settings', () => {
  const mockGroup = {
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
  } as GroupResponse;

  const mockSettings = {
    id: 's0000000-0000-0000-0000-000000000001',
    shg_id: mockGroup.id,
    monthly_saving_amount: '500.00',
    late_fine_per_day: '5.00',
    fine_grace_days: 5,
    default_interest_rate: '12.000',
    interest_type: 'REDUCING',
    max_loan_multiple: '3.0',
    min_tenure_months: 1,
    max_tenure_months: 24,
    processing_fee_percent: '1.00',
    penalty_interest_rate: '2.000',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-15T00:00:00Z',
  } as GroupSettingsResponse;

  const mockUsers: UserResponse[] = [
    {
      id: 'u1',
      email: 'admin@shg.org',
      phone: '9876543210',
      role: 'ADMIN',
      is_active: true,
    },
    {
      id: 'u2',
      email: 'leader@shg.org',
      phone: '9876543211',
      role: 'GROUP_LEADER',
      is_active: true,
    },
  ];

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
      items: [mockGroup],
      total: 1,
      page: 1,
      page_size: 20,
    });

    vi.spyOn(apiClient.groups, 'getSettings').mockResolvedValue(mockSettings);
    vi.spyOn(apiClient.groups, 'updateSettings').mockResolvedValue({
      ...mockSettings,
      monthly_saving_amount: '600.00',
    });

    vi.spyOn(apiClient.users, 'list').mockResolvedValue({
      items: mockUsers,
      total: 2,
      page: 1,
      page_size: 20,
    });
  });

  it('renders group rules form prefilled with current settings', async () => {
    render(
      <BrowserRouter>
        <SettingsPage />
      </BrowserRouter>
    );

    expect(screen.getByText('System & Group Settings')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByDisplayValue('500.00')).toBeInTheDocument();
      expect(screen.getByDisplayValue('12.000')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Reducing Balance (Diminishing)')).toBeInTheDocument();
      expect(screen.getByText('Save Group Policies')).toBeInTheDocument();
    });
  });

  it('updates group settings and shows success feedback', async () => {
    const updateSpy = vi.spyOn(apiClient.groups, 'updateSettings');

    render(
      <BrowserRouter>
        <SettingsPage />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('500.00')).toBeInTheDocument();
    });

    const savingInput = screen.getByDisplayValue('500.00');
    await userEvent.clear(savingInput);
    await userEvent.type(savingInput, '600');

    await userEvent.click(screen.getByText('Save Group Policies'));

    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith(
        mockGroup.id,
        expect.objectContaining({
          monthly_saving_amount: '600',
        })
      );
      expect(
        screen.getByText('Group financial rules and lending parameters saved successfully.')
      ).toBeInTheDocument();
    });
  });

  it('switches to Users Directory tab for ADMIN and lists users', async () => {
    render(
      <BrowserRouter>
        <SettingsPage />
      </BrowserRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Users Directory')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByText('Users Directory'));

    await waitFor(() => {
      expect(screen.getByText('Platform User Accounts')).toBeInTheDocument();
      expect(screen.getByText('admin@shg.org')).toBeInTheDocument();
      expect(screen.getByText('leader@shg.org')).toBeInTheDocument();
    });
  });
});
