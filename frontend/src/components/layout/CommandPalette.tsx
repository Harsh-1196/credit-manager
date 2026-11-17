import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth/AuthContext';
import { apiClient } from '../../lib/api/client';
import type { GroupResponse } from '../../lib/api/types';
import {
  Search,
  LayoutDashboard,
  Building2,
  Users,
  CheckSquare,
  FilePlus,
  Scale,
  ShieldCheck,
  Palette,
  FileSpreadsheet,
  Sliders,
  LogOut,
  Sun,
  X,
} from 'lucide-react';

interface CommandItem {
  id: string;
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  category: 'Navigation' | 'Actions' | 'Groups';
  action: () => void;
  allowedRoles?: string[];
}

export const CommandPalette: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [groups, setGroups] = useState<GroupResponse[]>([]);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  // Load groups for fast search
  useEffect(() => {
    if (user) {
      apiClient.groups
        .list()
        .then((res) => setGroups(res.items))
        .catch(() => {});
    }
  }, [user]);

  // Global Ctrl+K / Cmd+K shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const toggleTheme = () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('shg_theme', next);
    setIsOpen(false);
  };

  // Base command items
  const baseCommands: CommandItem[] = [
    {
      id: 'nav-dashboard',
      title: 'Dashboard Overview',
      subtitle: 'Corpus, trends, aging buckets and dues',
      icon: <LayoutDashboard className="w-4 h-4 text-[var(--primary)]" />,
      category: 'Navigation',
      action: () => {
        navigate('/dashboard');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-groups',
      title: 'Groups Directory',
      subtitle: 'View and manage Self-Help Groups',
      icon: <Building2 className="w-4 h-4 text-[var(--primary)]" />,
      category: 'Navigation',
      action: () => {
        navigate('/groups');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-members',
      title: 'Members Directory',
      subtitle: 'Member profiles, passbooks, and savings dues',
      icon: <Users className="w-4 h-4 text-[var(--primary)]" />,
      category: 'Navigation',
      allowedRoles: ['ADMIN', 'GROUP_LEADER', 'AUDITOR'],
      action: () => {
        navigate('/members');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-loan-apply',
      title: 'Apply for Loan',
      subtitle: 'Schedule preview, EMI calculations, and submission',
      icon: <FilePlus className="w-4 h-4 text-[var(--accent)]" />,
      category: 'Navigation',
      action: () => {
        navigate('/loans/apply');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-loan-approvals',
      title: 'Loan Approvals Queue',
      subtitle: 'Maker-checker loan approvals and disbursals',
      icon: <CheckSquare className="w-4 h-4 text-[var(--warning)]" />,
      category: 'Navigation',
      allowedRoles: ['ADMIN', 'GROUP_LEADER', 'AUDITOR'],
      action: () => {
        navigate('/loans/approvals');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-reports',
      title: 'Financial Reports & CSV Export',
      subtitle: 'Trial balance, ledger, statements, and aging',
      icon: <FileSpreadsheet className="w-4 h-4 text-[var(--primary)]" />,
      category: 'Navigation',
      action: () => {
        navigate('/reports');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-settings',
      title: 'System & Group Settings',
      subtitle: 'Interest rates, late fines, loan ceilings, users',
      icon: <Sliders className="w-4 h-4 text-[var(--ink)]" />,
      category: 'Navigation',
      allowedRoles: ['ADMIN', 'GROUP_LEADER'],
      action: () => {
        navigate('/settings');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-reconciliation',
      title: 'Ledger Reconciliation',
      subtitle: 'Discrepancy verification between domain and ledger',
      icon: <Scale className="w-4 h-4 text-[var(--accent)]" />,
      category: 'Navigation',
      allowedRoles: ['ADMIN'],
      action: () => {
        navigate('/reconciliation');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-audit',
      title: 'Audit Trail Logs',
      subtitle: 'Cryptographic hash chain tamper-evident events',
      icon: <ShieldCheck className="w-4 h-4 text-[var(--success)]" />,
      category: 'Navigation',
      allowedRoles: ['ADMIN', 'AUDITOR'],
      action: () => {
        navigate('/audit');
        setIsOpen(false);
      },
    },
    {
      id: 'nav-styleguide',
      title: 'Design Tokens & Styleguide',
      subtitle: 'Typography, palette, and component showcase',
      icon: <Palette className="w-4 h-4 text-[var(--muted-ink)]" />,
      category: 'Navigation',
      action: () => {
        navigate('/styleguide');
        setIsOpen(false);
      },
    },
    {
      id: 'act-theme',
      title: 'Toggle Color Theme',
      subtitle: 'Switch between light and dark mode',
      icon: <Sun className="w-4 h-4 text-[var(--warning)]" />,
      category: 'Actions',
      action: toggleTheme,
    },
    {
      id: 'act-logout',
      title: 'Sign Out',
      subtitle: 'End current authentication session',
      icon: <LogOut className="w-4 h-4 text-[var(--danger)]" />,
      category: 'Actions',
      action: () => {
        logout();
        setIsOpen(false);
      },
    },
  ];

  // Group direct navigation items
  const groupCommands: CommandItem[] = groups.map((g) => ({
    id: `group-${g.id}`,
    title: g.name,
    subtitle: `${g.village}, ${g.district} • Status: ${g.status}`,
    icon: <Building2 className="w-4 h-4 text-[var(--primary)]" />,
    category: 'Groups',
    action: () => {
      navigate(`/groups/${g.id}`);
      setIsOpen(false);
    },
  }));

  const allItems = [...baseCommands, ...groupCommands].filter((item) => {
    if (item.allowedRoles && user?.role && !item.allowedRoles.includes(user.role)) {
      return false;
    }
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      item.title.toLowerCase().includes(q) ||
      (item.subtitle && item.subtitle.toLowerCase().includes(q)) ||
      item.category.toLowerCase().includes(q)
    );
  });

  // Handle arrow keys
  const handleKeyDownList = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev < allItems.length - 1 ? prev + 1 : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev > 0 ? prev - 1 : allItems.length - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (allItems[selectedIndex]) {
        allItems[selectedIndex].action();
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-black/50 backdrop-blur-sm"
      onClick={() => setIsOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command Palette"
    >
      <div
        className="bg-[var(--surface)] border border-[var(--border)] rounded-xl w-full max-w-xl shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDownList}
      >
        {/* Search Input */}
        <div className="flex items-center px-4 py-3 border-b border-[var(--border)]">
          <Search className="w-5 h-5 text-[var(--muted-ink)] shrink-0 mr-3" />
          <input
            ref={inputRef}
            type="text"
            placeholder="Type a command or search..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            className="w-full bg-transparent text-sm text-[var(--ink)] placeholder-[var(--muted-ink)] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="text-[var(--muted-ink)] hover:text-[var(--ink)] ml-2"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto p-2 divide-y divide-[var(--border)]">
          {allItems.length === 0 ? (
            <div className="py-8 text-center text-xs text-[var(--muted-ink)]">
              No matching commands or pages found.
            </div>
          ) : (
            allItems.map((item, idx) => {
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={item.id}
                  onClick={item.action}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer transition-colors ${
                    isSelected
                      ? 'bg-[var(--primary-tint)] text-[var(--primary)]'
                      : 'hover:bg-[var(--surface-muted)] text-[var(--ink)]'
                  }`}
                >
                  <div className="shrink-0">{item.icon}</div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold leading-tight truncate">{item.title}</p>
                    {item.subtitle && (
                      <p className="text-[11px] text-[var(--muted-ink)] truncate mt-0.5">
                        {item.subtitle}
                      </p>
                    )}
                  </div>
                  <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-[var(--surface-muted)] text-[var(--muted-ink)] border border-[var(--border)] shrink-0">
                    {item.category}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* Footer info */}
        <div className="px-4 py-2 border-t border-[var(--border)] bg-[var(--surface-muted)] flex items-center justify-between text-[11px] text-[var(--muted-ink)]">
          <span>Navigate with ↑ and ↓, Enter to select</span>
          <span>Esc to exit</span>
        </div>
      </div>
    </div>
  );
};
