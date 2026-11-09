import React from 'react';
import { useAuth } from '../../lib/auth/AuthContext';
import { ThemeToggle } from '../ui/ThemeToggle';
import { Breadcrumbs } from './Breadcrumbs';
import { Button } from '../ui/Button';
import { LogOut } from 'lucide-react';

export const Header: React.FC = () => {
  const { user, logout } = useAuth();

  return (
    <header className="h-14 border-b border-[var(--border)] bg-[var(--surface)] px-6 flex items-center justify-between sticky top-0 z-10">
      <div className="flex items-center">
        <Breadcrumbs />
      </div>

      <div className="flex items-center space-x-3">
        <ThemeToggle />

        {user && (
          <div className="flex items-center space-x-3 pl-3 border-l border-[var(--border)]">
            <div className="text-right hidden sm:block">
              <div className="text-xs font-semibold text-[var(--ink)] leading-none">
                {user.email.split('@')[0]}
              </div>
              <div className="text-[10px] text-[var(--muted-ink)] font-mono uppercase mt-0.5">
                {user.role}
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              title="Sign Out"
              aria-label="Sign Out"
              className="text-[var(--muted-ink)] hover:text-[var(--danger)]"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden md:inline ml-1 text-xs">Logout</span>
            </Button>
          </div>
        )}
      </div>
    </header>
  );
};
