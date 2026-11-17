import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DraftNotesModal } from '../src/features/meetings/DraftNotesModal';
import { apiClient } from '../src/lib/api/client';
import type { DraftCollectionResponse } from '../src/lib/api/types';

describe('Draft Collection from Notes Modal (Phase 6b)', () => {
  const mockMeetingId = 'm0000000-0000-0000-0000-000000000001';
  const mockOnApply = vi.fn();
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.restoreAllMocks();
    mockOnApply.mockReset();
    mockOnClose.mockReset();
  });

  it('renders modal with textarea, disclaimer, and sample notes button', async () => {
    render(
      <DraftNotesModal
        isOpen={true}
        onClose={mockOnClose}
        meetingId={mockMeetingId}
        shgName="Udaan Mahila Mandal"
        onApplyDraft={mockOnApply}
      />
    );

    expect(screen.getByText('Draft Collection from Notes')).toBeInTheDocument();
    expect(screen.getByText(/Human Review Required:/i)).toBeInTheDocument();
    expect(screen.getByText(/Insert sample notes/i)).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/Radha paid 500 savings/i);
    expect(textarea).toBeInTheDocument();

    // Clicking sample notes inserts text
    await userEvent.click(screen.getByText(/Insert sample notes/i));
    expect((textarea as HTMLTextAreaElement).value).toContain('Radha paid 500 savings');
  });

  it('calls AI draft-collection API and displays extracted amounts, unmatched items, and ambiguous names', async () => {
    const mockDraftResponse: DraftCollectionResponse = {
      meeting_id: mockMeetingId,
      shg_id: 'g0000000-0000-0000-0000-000000000001',
      shg_name: 'Udaan Mahila Mandal',
      meeting_date: '2026-03-15',
      items: [
        {
          member_id: 'mem-1',
          member_name: 'Radha Devi',
          attendance: 'PRESENT',
          savings_amount: '500.00',
          loan_repayment_amount: '1100.00',
          fine_amount: '0.00',
          total_amount: '1600.00',
          confidence: 1.0,
        },
        {
          member_id: 'mem-2',
          member_name: 'Geeta Sharma',
          attendance: 'ABSENT',
          savings_amount: '0.00',
          loan_repayment_amount: '0.00',
          fine_amount: '0.00',
          total_amount: '0.00',
          confidence: 1.0,
        },
      ],
      unmatched_items: [
        {
          raw_text: 'Unknown person Suresh gave 1000',
          reason: 'UNMATCHED_MEMBER',
          candidate_names: [],
          detected_amount: '1000.00',
        },
      ],
      ambiguous_members: ['Sunita'],
      total_collected_draft: '1600.00',
      disclaimer: 'This is an uncommitted AI draft generated from notes.',
    };

    vi.spyOn(apiClient.ai, 'draftCollection').mockResolvedValue(mockDraftResponse);

    render(
      <DraftNotesModal
        isOpen={true}
        onClose={mockOnClose}
        meetingId={mockMeetingId}
        shgName="Udaan Mahila Mandal"
        onApplyDraft={mockOnApply}
      />
    );

    const textarea = screen.getByPlaceholderText(/Radha paid 500 savings/i);
    await userEvent.type(textarea, 'Radha 500 savings and 1100 emi. Geeta absent.');

    const extractBtn = screen.getByRole('button', { name: /Extract with AI/i });
    await userEvent.click(extractBtn);

    // Verify extraction API was called
    expect(apiClient.ai.draftCollection).toHaveBeenCalledWith({
      meeting_id: mockMeetingId,
      notes: 'Radha 500 savings and 1100 emi. Geeta absent.',
    });

    // Check extracted items in table
    await waitFor(() => {
      expect(screen.getByText('Radha Devi')).toBeInTheDocument();
      expect(screen.getByText('Geeta Sharma')).toBeInTheDocument();
      expect(screen.getByText('ABSENT')).toBeInTheDocument();
    });

    // Check unmatched items warning
    expect(screen.getByText(/Unmatched Notes \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Unknown person Suresh gave 1000/i)).toBeInTheDocument();

    // Check ambiguous members warning
    expect(screen.getByText(/Ambiguous Member Names \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Multiple members match/i)).toBeInTheDocument();
    expect(screen.getByText(/"Sunita"/i)).toBeInTheDocument();

    // Click "Apply to Collection Sheet"
    const applyBtn = screen.getByRole('button', { name: /Apply to Collection Sheet/i });
    await userEvent.click(applyBtn);

    expect(mockOnApply).toHaveBeenCalledWith(mockDraftResponse);
    expect(mockOnClose).toHaveBeenCalled();
  });
});
