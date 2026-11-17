import React from 'react';
import { useAuth } from '../../lib/auth/AuthContext';
import { ThemeToggle } from '../ui/ThemeToggle';
import { Breadcrumbs } from './Breadcrumbs';
import { Button } from '../ui/Button';
import { LogOut, Search, Sparkles } from 'lucide-react';
import { WorkerStatusIndicator } from '../../features/system/WorkerStatusIndicator';
import { useAssistant } from '../../features/ai/AssistantContext';

export const Header: React.FC = () => {
  const { user, logout } = useAuth();
  let assistant: ReturnType<typeof useAssistant> | null = null;
  try {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    assistant = useAssistant();
  } catch {
    assistant = null;
  }

  const openPalette = () => {
    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'k',
        ctrlKey: true,
        bubbles: true,
      })
    );
  };

  return (
    <header className="h-14 border-b border-[var(--border)] bg-[var(--surface)] px-6 flex items-center justify-between sticky top-0 z-10">
      <div className="flex items-center space-x-4">
        <Breadcrumbs />
      </div>

      <div className="flex items-center space-x-3">
        {user && (
          <button
            type="button"
            onClick={openPalette}
            className="flex items-center gap-2 px-3 py-1.5 text-xs rounded border border-[var(--border)] bg-[var(--surface-muted)] text-[var(--muted-ink)] hover:text-[var(--ink)] hover:border-[var(--primary)] transition-colors"
            title="Press Ctrl+K or Cmd+K to search"
            aria-label="Search and command palette (Ctrl+K)"
          >
            <Search className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Search commands...</span>
            <kbd className="hidden sm:inline-block font-mono text-[10px] bg-[var(--surface)] border border-[var(--border)] px-1 py-0.5 rounded text-[var(--muted-ink)]">
              Ctrl K
            </kbd>
          </button>
        )}

        {user && assistant && (
          <button
            type="button"
            onClick={() => assistant?.toggleAssistant()}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded border border-[var(--border)] bg-[var(--surface-muted)] text-[var(--primary)] hover:border-[var(--primary)] hover:bg-[var(--surface)] transition-colors font-medium shadow-2xs"
            title="Ask AI Assistant"
            aria-label="Open AI Assistant"
          >
            <Sparkles className="w-3.5 h-3.5 text-[var(--primary)]" />
            <span className="hidden md:inline">AI Assistant</span>
          </button>
        )}

        {user && <WorkerStatusIndicator />}
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
