import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuditLogPage } from '../src/features/audit/AuditLogPage';
import { apiClient } from '../src/lib/api/client';
import type { AuditLogRowResponse } from '../src/lib/api/types';

describe('Screen 11: Audit Trail & Chain Verification', () => {
  const sampleAuditLogs: AuditLogRowResponse[] = [
    {
      id: 'a0000000-0000-0000-0000-000000000001',
      occurred_at: '2026-03-01T10:00:00Z',
      actor_id: 'u0000000-0000-0000-0000-000000000001',
      actor_role: 'GROUP_LEADER',
      action: 'APPROVE',
      entity_type: 'LOAN',
      entity_id: 'l0000000-0000-0000-0000-000000000001',
      before: { status: 'SUBMITTED', approved_by: null },
      after: { status: 'APPROVED', approved_by: 'u0000000-0000-0000-0000-000000000001' },
      ip: '192.168.1.1',
      user_agent: 'VitestAgent/1.0',
      request_id: 'req-12345',
      prev_hash: '0'.repeat(64),
      row_hash: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
    },
    {
      id: 'a0000000-0000-0000-0000-000000000002',
      occurred_at: '2026-03-01T10:15:00Z',
      actor_id: 'u0000000-0000-0000-0000-000000000001',
      actor_role: 'GROUP_LEADER',
      action: 'DISBURSE',
      entity_type: 'LOAN',
      entity_id: 'l0000000-0000-0000-0000-000000000001',
      before: { status: 'APPROVED' },
      after: { status: 'ACTIVE', disbursed_amount: '50000.00' },
      ip: '192.168.1.1',
      user_agent: 'VitestAgent/1.0',
      request_id: 'req-12346',
      prev_hash: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
      row_hash: '123456abcdef7890123456abcdef7890123456abcdef7890123456abcdef7890',
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(apiClient.audit, 'list').mockResolvedValue({
      items: sampleAuditLogs,
      total: 2,
      limit: 15,
      offset: 0,
    });
    vi.spyOn(apiClient.audit, 'verify').mockResolvedValue({
      valid: true,
      count: 2,
      broken_at_index: null,
      broken_at_id: null,
      error: null,
      message: 'All 2 audit log records cryptographically verified with unbroken SHA-256 chain.',
    });
    vi.spyOn(apiClient.audit, 'exportCsv').mockResolvedValue(
      new Blob(['id,action,entity_type\n1,APPROVE,LOAN'], { type: 'text/csv' })
    );
  });

  it('renders audit trail page with rows, hashes, and actions', async () => {
    render(<AuditLogPage />);

    expect(screen.getByText('Audit Trail & Chain Verification')).toBeInTheDocument();
    expect(screen.getByText('Tamper-evident append-only ledger secured via SHA-256 cryptographic hash chaining')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('APPROVE')).toBeInTheDocument();
      expect(screen.getByText('DISBURSE')).toBeInTheDocument();
    });

    expect(screen.getAllByText('LOAN').length).toBeGreaterThan(0);
    expect(screen.getByText(/abcdef123456/)).toBeInTheDocument();
  });

  it('opens before/after state diff drawer when a row is clicked', async () => {
    const user = userEvent.setup();
    render(<AuditLogPage />);

    await waitFor(() => {
      expect(screen.getByRole('cell', { name: 'APPROVE' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('cell', { name: 'APPROVE' }));

    await waitFor(() => {
      expect(screen.getByText('Audit Entry Details & State Diff')).toBeInTheDocument();
      expect(screen.getByText('Before State')).toBeInTheDocument();
      expect(screen.getByText('After State')).toBeInTheDocument();
    });

    // Verify before/after contents
    expect(screen.getByText(/"status": "SUBMITTED"/)).toBeInTheDocument();
    expect(screen.getByText(/"status": "APPROVED"/)).toBeInTheDocument();

    // Close drawer
    await user.click(screen.getByText('Close Drawer'));
    await waitFor(() => {
      expect(screen.queryByText('Audit Entry Details & State Diff')).not.toBeInTheDocument();
    });
  });

  it('triggers cryptographic verification and displays chain verified badge', async () => {
    const user = userEvent.setup();
    render(<AuditLogPage />);

    expect(screen.getByText('Unverified this session')).toBeInTheDocument();

    const verifyBtn = screen.getByRole('button', { name: /verify now/i });
    await user.click(verifyBtn);

    await waitFor(() => {
      expect(screen.getByText(/Chain Verified \(2 rows\)/)).toBeInTheDocument();
      expect(screen.getByText(/All 2 audit log records cryptographically verified/)).toBeInTheDocument();
    });

    expect(apiClient.audit.verify).toHaveBeenCalledTimes(1);
  });

  it('triggers CSV export when clicking Export CSV button', async () => {
    const user = userEvent.setup();
    // Mock URL.createObjectURL and revokeObjectURL
    window.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    window.URL.revokeObjectURL = vi.fn();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    render(<AuditLogPage />);

    const exportBtn = screen.getByRole('button', { name: /export csv/i });
    await user.click(exportBtn);

    await waitFor(() => {
      expect(apiClient.audit.exportCsv).toHaveBeenCalledTimes(1);
    });
    clickSpy.mockRestore();
  });
});
