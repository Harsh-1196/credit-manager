import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { Sidebar } from '../src/components/layout/Sidebar';
import * as AuthContextModule from '../src/lib/auth/AuthContext';
import type { UserRole } from '../src/lib/api/types';

describe('Sidebar Role Scoping', () => {
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

  it('ADMIN sees Groups, Members, User Directory, Audit Trail', () => {
    mockAuthForRole('ADMIN');
    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText('Groups')).toBeInTheDocument();
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(screen.getByText('User Directory')).toBeInTheDocument();
    expect(screen.getByText('Audit Trail')).toBeInTheDocument();
  });

  it('GROUP_LEADER sees Groups and Members, but NOT User Directory or Audit Trail', () => {
    mockAuthForRole('GROUP_LEADER');
    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText('Groups')).toBeInTheDocument();
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(screen.queryByText('User Directory')).not.toBeInTheDocument();
    expect(screen.queryByText('Audit Trail')).not.toBeInTheDocument();
  });

  it('AUDITOR sees Groups, Members, and Audit Trail, but NOT User Directory', () => {
    mockAuthForRole('AUDITOR');
    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText('Groups')).toBeInTheDocument();
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(screen.getByText('Audit Trail')).toBeInTheDocument();
    expect(screen.queryByText('User Directory')).not.toBeInTheDocument();
  });

  it('MEMBER sees My Group, but NOT Member Directory, User Directory, or Audit Trail', () => {
    mockAuthForRole('MEMBER');
    render(
      <BrowserRouter>
        <Sidebar />
      </BrowserRouter>
    );

    expect(screen.getByText('My Group')).toBeInTheDocument();
    expect(screen.queryByText('User Directory')).not.toBeInTheDocument();
    expect(screen.queryByText('Audit Trail')).not.toBeInTheDocument();
  });
});
