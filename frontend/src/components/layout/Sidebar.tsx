import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../lib/auth/AuthContext';
import {
  Users,
  Building2,
  ShieldCheck,
  Palette,
  UserCheck,
  CheckSquare,
  FilePlus,
} from 'lucide-react';

export const Sidebar: React.FC = () => {
  const { user } = useAuth();
  const role = user?.role;

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-3 py-2 text-sm font-medium rounded transition-colors ${
      isActive
        ? 'bg-[var(--accent-subtle)] text-[var(--primary)] font-semibold'
        : 'text-[var(--muted-ink)] hover:text-[var(--ink)] hover:bg-[var(--surface-muted)]'
    }`;

  return (
    <aside className="w-64 border-r border-[var(--border)] bg-[var(--surface)] flex flex-col h-screen sticky top-0 shrink-0">
      {/* Brand Header */}
      <div className="p-4 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-[var(--primary)] text-[var(--surface)] flex items-center justify-center font-serif font-bold text-lg">
            S
          </div>
          <div>
            <h1 className="font-serif font-semibold text-[var(--ink)] text-base leading-tight">
              SHG Credit
            </h1>
            <p className="text-[10px] uppercase tracking-wider text-[var(--muted-ink)] font-mono">
              Self-Help Group Ledger
            </p>
          </div>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        <div className="px-3 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)]">
          Operations
        </div>

        <NavLink to="/groups" className={navLinkClass}>
          <Building2 className="w-4 h-4 shrink-0" />
          <span>{role === 'MEMBER' ? 'My Group' : 'Groups'}</span>
        </NavLink>

        {(role === 'ADMIN' || role === 'GROUP_LEADER' || role === 'AUDITOR') && (
          <>
            <NavLink to="/members" className={navLinkClass}>
              <Users className="w-4 h-4 shrink-0" />
              <span>Members</span>
            </NavLink>
            <NavLink to="/loans/approvals" className={navLinkClass}>
              <CheckSquare className="w-4 h-4 shrink-0" />
              <span>Loan Approvals</span>
            </NavLink>
          </>
        )}

        <NavLink to="/loans/apply" className={navLinkClass}>
          <FilePlus className="w-4 h-4 shrink-0" />
          <span>Apply for Loan</span>
        </NavLink>

        {role === 'ADMIN' && (
          <>
            <div className="px-3 pt-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)]">
              Administration
            </div>
            <NavLink to="/users" className={navLinkClass}>
              <UserCheck className="w-4 h-4 shrink-0" />
              <span>User Directory</span>
            </NavLink>
          </>
        )}

        {(role === 'ADMIN' || role === 'AUDITOR') && (
          <NavLink to="/audit" className={navLinkClass}>
            <ShieldCheck className="w-4 h-4 shrink-0" />
            <span>Audit Trail</span>
          </NavLink>
        )}

        <div className="px-3 pt-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted-ink)]">
          System
        </div>
        <NavLink to="/styleguide" className={navLinkClass}>
          <Palette className="w-4 h-4 shrink-0" />
          <span>Design Tokens</span>
        </NavLink>
      </nav>

      {/* User Status in Sidebar Footer */}
      {user && (
        <div className="p-3 border-t border-[var(--border)] bg-[var(--surface-muted)] text-xs">
          <div className="flex flex-col gap-0.5">
            <span className="font-medium text-[var(--ink)] truncate">{user.email}</span>
            <span className="inline-block px-1.5 py-0.5 text-[10px] font-mono tracking-wide rounded bg-[var(--surface)] text-[var(--primary)] border border-[var(--border)] w-max">
              {user.role}
            </span>
          </div>
        </div>
      )}
    </aside>
  );
};
