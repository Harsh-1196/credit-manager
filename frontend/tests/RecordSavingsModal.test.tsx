import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { RecordSavingsModal } from '../src/features/savings/RecordSavingsModal';
import { api } from '../src/lib/api/client';

vi.mock('../src/lib/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api/client')>('../src/lib/api/client');
  return {
    ...actual,
    api: {
      savings: {
        collect: vi.fn(),
      },
    },
  };
});

describe('RecordSavingsModal', () => {
  const onClose = vi.fn();
  const onSuccess = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.savings.collect).mockResolvedValue({
      due: { id: 'due-1' },
      new_savings_balance: '500.00',
      message: 'Success',
    } as any);
  });

  it('renders Step 1 form fields and proceeds to Step 2 confirmation', async () => {
    render(
      <RecordSavingsModal
        memberId="mem-1"
        memberName="Radha Sharma"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    expect(screen.getByRole('heading', { name: /record savings deposit/i })).toBeInTheDocument();
    expect(screen.getByText('Radha Sharma')).toBeInTheDocument();

    const amountInput = screen.getByLabelText(/deposit amount/i);
    const reviewBtn = screen.getByRole('button', { name: /review transaction/i });

    fireEvent.change(amountInput, { target: { value: '350.00' } });
    fireEvent.click(reviewBtn);

    // Should transition to confirm step
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /confirm savings deposit/i })).toBeInTheDocument();
      expect(screen.getByText(/total cash collected/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /confirm & post/i })).toBeInTheDocument();
    });

    // Click confirm & post
    const confirmBtn = screen.getByRole('button', { name: /confirm & post/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.savings.collect).toHaveBeenCalledWith(
        expect.objectContaining({
          member_id: 'mem-1',
          amount: '350.00',
        }),
        expect.any(String) // client-side idempotency key
      );
      expect(onSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('allows stepping back from confirmation to edit form', async () => {
    render(
      <RecordSavingsModal
        memberId="mem-1"
        memberName="Radha Sharma"
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    const reviewBtn = screen.getByRole('button', { name: /review transaction/i });
    fireEvent.click(reviewBtn);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /back/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /record savings deposit/i })).toBeInTheDocument();
    });
  });
});
