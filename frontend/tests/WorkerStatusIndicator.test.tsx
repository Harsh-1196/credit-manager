import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkerStatusIndicator } from '../src/features/system/WorkerStatusIndicator';
import { apiClient } from '../src/lib/api/client';
import type { WorkerStatusResponse } from '../src/lib/api/types';

describe('WorkerStatusIndicator Component', () => {
  const mockStatus: WorkerStatusResponse = {
    worker_status: 'HEALTHY',
    pending_events_count: 3,
    processing_events_count: 1,
    failed_events_count: 0,
    dead_letter_count: 0,
    lag_seconds: 0.2,
    last_event_processed_at: '2026-03-01T12:00:00Z',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient.system, 'getWorkerStatus').mockResolvedValue(mockStatus);
  });

  it('renders worker healthy badge and lag indicator', async () => {
    render(<WorkerStatusIndicator />);

    await waitFor(() => {
      expect(screen.getByText('Worker Healthy')).toBeInTheDocument();
      expect(screen.getByText(/Lag:\s*0\.2s/)).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument(); // pending badge
    });
  });

  it('opens worker diagnostics dialog when clicked', async () => {
    const user = userEvent.setup();
    render(<WorkerStatusIndicator />);

    await waitFor(() => {
      expect(screen.getByText('Worker Healthy')).toBeInTheDocument();
    });

    const triggerBtn = screen.getByRole('button', { name: /outbox worker status/i });
    await user.click(triggerBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /worker diagnostics/i })).toBeInTheDocument();
      expect(screen.getByText('Outbox & Worker Status')).toBeInTheDocument();
      expect(screen.getByText('0.20s')).toBeInTheDocument();
    });
  });
});
