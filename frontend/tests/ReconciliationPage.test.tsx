import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ReconciliationPage } from '../src/features/reconciliation/ReconciliationPage';
import { apiClient } from '../src/lib/api/client';
import type { ReconciliationRunResponse } from '../src/lib/api/types';

describe('Screen: ADMIN Reconciliation Panel', () => {
  const cleanRun: ReconciliationRunResponse = {
    id: 'r0000000-0000-0000-0000-000000000001',
    run_at: '2026-03-01T12:00:00Z',
    triggered_by: 'u0000000-0000-0000-0000-000000000001',
    status: 'COMPLETED',
    groups_checked_count: 5,
    discrepancies_count: 0,
    discrepancies: [],
    execution_time_ms: 120,
    notes: 'Reconciliation completed cleanly',
  };

  const discrepantRun: ReconciliationRunResponse = {
    id: 'r0000000-0000-0000-0000-000000000002',
    run_at: '2026-03-01T12:05:00Z',
    triggered_by: 'u0000000-0000-0000-0000-000000000001',
    status: 'DISCREPANCIES_FOUND',
    groups_checked_count: 5,
    discrepancies_count: 1,
    discrepancies: [
      {
        shg_id: 'g0000000-0000-0000-0000-000000000001',
        shg_name: 'Pragati Mahila Mandal',
        entity_type: 'MEMBER_SAVINGS',
        entity_id: 'm0000000-0000-0000-0000-000000000001',
        member_name: 'Sunita Devi',
        ledger_value: '5000.00',
        domain_value: '4500.00',
        difference: '500.00',
        explanation: 'Member savings passbook differs from posted journal lines by 500.00',
      },
    ],
    execution_time_ms: 155,
    notes: 'Discrepancies found',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient.reconciliation, 'getLatest').mockResolvedValue(cleanRun);
    vi.spyOn(apiClient.reconciliation, 'listRuns').mockResolvedValue([cleanRun]);
    vi.spyOn(apiClient.reconciliation, 'run').mockResolvedValue(discrepantRun);
  });

  it('renders clean reconciliation empty state when no discrepancies exist', async () => {
    render(<ReconciliationPage />);

    expect(screen.getByText('Ledger & Read-Model Reconciliation')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('All accounts, loan schedules, and read models reconcile cleanly.')).toBeInTheDocument();
      expect(screen.getAllByText('CONSISTENT').length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText('5').length).toBeGreaterThan(0); // Groups checked
    expect(screen.getAllByText('120 ms').length).toBeGreaterThan(0);
  });

  it('renders discrepancy table when discrepancies are detected', async () => {
    vi.spyOn(apiClient.reconciliation, 'getLatest').mockResolvedValue(discrepantRun);
    vi.spyOn(apiClient.reconciliation, 'listRuns').mockResolvedValue([discrepantRun]);

    render(<ReconciliationPage />);

    await waitFor(() => {
      expect(screen.getByText('Detected Discrepancies (1)')).toBeInTheDocument();
      expect(screen.getByText('MEMBER_SAVINGS')).toBeInTheDocument();
      expect(screen.getByText('Sunita Devi')).toBeInTheDocument();
      expect(screen.getByText('Pragati Mahila Mandal')).toBeInTheDocument();
      expect(screen.getByText('₹5000.00')).toBeInTheDocument();
      expect(screen.getByText('₹4500.00')).toBeInTheDocument();
      expect(screen.getByText('₹500.00')).toBeInTheDocument();
    });
  });

  it('triggers manual reconciliation run when button clicked', async () => {
    const user = userEvent.setup();
    render(<ReconciliationPage />);

    await waitFor(() => {
      expect(screen.getByText('All accounts, loan schedules, and read models reconcile cleanly.')).toBeInTheDocument();
    });

    const runBtn = screen.getByRole('button', { name: /run reconciliation now/i });
    await user.click(runBtn);

    await waitFor(() => {
      expect(apiClient.reconciliation.run).toHaveBeenCalledTimes(1);
      expect(screen.getByText('Detected Discrepancies (1)')).toBeInTheDocument();
    });
  });
});
