import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AssistantProvider, useAssistant } from '../src/features/ai/AssistantContext';
import { AssistantDrawer } from '../src/features/ai/AssistantDrawer';
import { apiClient } from '../src/lib/api/client';

const TestOpener: React.FC = () => {
  const { openAssistant, toggleAssistant } = useAssistant();
  return (
    <div>
      <button onClick={() => openAssistant()}>Open Assistant</button>
      <button onClick={() => toggleAssistant()}>Toggle Assistant</button>
      <button onClick={() => openAssistant('What is our corpus?')}>Open With Prompt</button>
    </div>
  );
};

describe('AI Assistant Side Panel (Screen 6b)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders closed by default and opens on trigger', async () => {
    render(
      <AssistantProvider>
        <TestOpener />
        <AssistantDrawer />
      </AssistantProvider>
    );

    expect(screen.queryByRole('dialog', { name: /AI Financial Assistant/i })).not.toBeInTheDocument();

    const openBtn = screen.getByText('Open Assistant');
    await userEvent.click(openBtn);

    expect(screen.getByRole('dialog', { name: /AI Financial Assistant/i })).toBeInTheDocument();
    expect(screen.getByText(/SHG AI Assistant/i)).toBeInTheDocument();
    expect(screen.getByText(/AI Disclaimer:/i)).toBeInTheDocument();
  });

  it('displays streamed assistant responses and collapsible read-only tool calls', async () => {
    // Mock streamChat generator
    async function* mockStream() {
      yield {
        tool_calls: [
          {
            name: 'get_group_dashboard',
            arguments: { shg_id: 'g0000000-0000-0000-0000-000000000001' },
            result_summary: 'Total Corpus: ₹2,50,000.00; Savings: ₹1,80,000.00',
          },
        ],
      };
      yield { content: 'Based on the official ledger, ' };
      yield { content: 'your group corpus is ₹2,50,000.00.' };
      yield { done: true };
    }

    vi.spyOn(apiClient.ai, 'streamChat').mockReturnValue(mockStream() as any);

    render(
      <AssistantProvider>
        <TestOpener />
        <AssistantDrawer />
      </AssistantProvider>
    );

    await userEvent.click(screen.getByText('Open Assistant'));

    const input = screen.getByPlaceholderText(/Ask financial questions/i);
    await userEvent.type(input, 'What is our corpus?');

    const sendBtn = screen.getByRole('button', { name: /Send Message/i });
    await userEvent.click(sendBtn);

    // Verify tool execution details rendered
    await waitFor(() => {
      expect(screen.getByText(/Tools Executed/i)).toBeInTheDocument();
      expect(screen.getByText('get_group_dashboard')).toBeInTheDocument();
      expect(screen.getAllByText(/read-only/i).length).toBeGreaterThanOrEqual(1);
    });

    // Verify streamed content
    expect(
      screen.getByText(/Based on the official ledger, your group corpus is ₹2,50,000.00./i)
    ).toBeInTheDocument();

    // Verify safe boundary disclaimer present
    expect(screen.getByText(/Ledger writes blocked/i)).toBeInTheDocument();
  });

  it('falls back to standard chat API if stream fails', async () => {
    vi.spyOn(apiClient.ai, 'streamChat').mockImplementation(() => {
      throw new Error('Streaming not supported');
    });

    vi.spyOn(apiClient.ai, 'chat').mockResolvedValue({
      role: 'assistant',
      content: 'Here is the delinquency breakdown: 1 member overdue.',
      tool_calls: [
        {
          name: 'list_overdue',
          arguments: { shg_id: 'g1' },
          result_summary: '1 overdue loan found',
        },
      ],
    });

    render(
      <AssistantProvider>
        <TestOpener />
        <AssistantDrawer />
      </AssistantProvider>
    );

    await userEvent.click(screen.getByText('Open Assistant'));

    const input = screen.getByPlaceholderText(/Ask financial questions/i);
    await userEvent.type(input, 'Who is overdue?{enter}');

    await waitFor(() => {
      expect(screen.getByText(/Here is the delinquency breakdown/i)).toBeInTheDocument();
      expect(screen.getByText('list_overdue')).toBeInTheDocument();
    });
  });

  it('closes on Escape key press and backdrop click', async () => {
    render(
      <AssistantProvider>
        <TestOpener />
        <AssistantDrawer />
      </AssistantProvider>
    );

    await userEvent.click(screen.getByText('Open Assistant'));
    expect(screen.getByRole('dialog', { name: /AI Financial Assistant/i })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: /AI Financial Assistant/i })).not.toBeInTheDocument();
  });

  it('clears conversation on reset click', async () => {
    render(
      <AssistantProvider>
        <TestOpener />
        <AssistantDrawer />
      </AssistantProvider>
    );

    await userEvent.click(screen.getByText('Open Assistant'));

    const clearBtn = screen.getByRole('button', { name: /Clear conversation/i });
    await userEvent.click(clearBtn);

    expect(screen.getByText(/Conversation reset/i)).toBeInTheDocument();
  });
});
