import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { CommandPalette } from '../src/components/layout/CommandPalette';
import { apiClient } from '../src/lib/api/client';
import * as AuthContextModule from '../src/lib/auth/AuthContext';

const mockedNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const original = await importOriginal<Record<string, any>>();
  return {
    ...original,
    useNavigate: () => mockedNavigate,
  };
});

describe('Command Palette (Ctrl+K)', () => {
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
  } as any;

  beforeEach(() => {
    vi.restoreAllMocks();
    mockedNavigate.mockReset();

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
  });

  it('opens command palette on Ctrl+K keyboard shortcut', async () => {
    render(
      <BrowserRouter>
        <CommandPalette />
      </BrowserRouter>
    );

    // Initially closed
    expect(screen.queryByPlaceholderText('Type a command or search...')).not.toBeInTheDocument();

    // Trigger Ctrl+K
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type a command or search...')).toBeInTheDocument();
      expect(screen.getByText('Dashboard Overview')).toBeInTheDocument();
      expect(screen.getByText('Financial Reports & CSV Export')).toBeInTheDocument();
    });
  });

  it('filters commands when typing in query input and navigates on Enter', async () => {
    render(
      <BrowserRouter>
        <CommandPalette />
      </BrowserRouter>
    );

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type a command or search...')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Type a command or search...');
    await userEvent.type(searchInput, 'Reports');

    expect(screen.getByText('Financial Reports & CSV Export')).toBeInTheDocument();
    expect(screen.queryByText('Apply for Loan')).not.toBeInTheDocument();

    // Press Enter to navigate
    fireEvent.keyDown(searchInput, { key: 'Enter' });

    expect(mockedNavigate).toHaveBeenCalledWith('/reports');
  });

  it('closes on Escape key press', async () => {
    render(
      <BrowserRouter>
        <CommandPalette />
      </BrowserRouter>
    );

    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type a command or search...')).toBeInTheDocument();
    });

    fireEvent.keyDown(window, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Type a command or search...')).not.toBeInTheDocument();
    });
  });
});
