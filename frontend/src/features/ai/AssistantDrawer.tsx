import React, { useState, useEffect, useRef } from 'react';
import { api, ApiException } from '../../lib/api/client';
import type { ChatMessage, ToolCallRecord } from '../../lib/api/types';
import { useAssistant } from './AssistantContext';
import { Button } from '../../components/ui/Button';
import {
  Sparkles,
  X,
  Send,
  Wrench,
  AlertTriangle,
  RotateCcw,
  CheckCircle2,
  ChevronRight,
  HelpCircle,
} from 'lucide-react';

interface DisplayMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  toolCalls?: ToolCallRecord[];
  isStreaming?: boolean;
}

export const AssistantDrawer: React.FC = () => {
  const { isOpen, closeAssistant, activeShgId, initialPrompt, clearInitialPrompt } = useAssistant();
  const [messages, setMessages] = useState<DisplayMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        'Hello! I am your SHG Financial Assistant. I can look up member passbooks, delinquency reports, portfolio metrics (PAR 30/60/90), and meeting dues using read-only ledger tools. How can I help you today?',
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen, messages]);

  // Handle initial prompt if opened with one
  useEffect(() => {
    if (isOpen && initialPrompt) {
      setInput(initialPrompt);
      clearInitialPrompt();
    }
  }, [isOpen, initialPrompt, clearInitialPrompt]);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        closeAssistant();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeAssistant]);

  const handleSend = async (textToSend?: string) => {
    const userPrompt = (textToSend || input).trim();
    if (!userPrompt || isLoading) return;

    setError(null);
    setInput('');

    const userMessage: DisplayMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: userPrompt,
    };

    const assistantId = `ast-${Date.now()}`;
    const initialAssistantMessage: DisplayMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      toolCalls: [],
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMessage, initialAssistantMessage]);
    setIsLoading(true);

    const apiMessages: ChatMessage[] = [
      ...messages
        .filter((m) => m.id !== 'welcome')
        .map((m) => ({ role: m.role, content: m.content })),
      { role: 'user', content: userPrompt },
    ];

    try {
      // Try streaming generator
      let streamedContent = '';
      let collectedTools: ToolCallRecord[] = [];
      let streamSucceeded = false;

      try {
        const stream = api.ai.streamChat({
          messages: apiMessages,
          shg_id: activeShgId || undefined,
        });

        for await (const chunk of stream) {
          streamSucceeded = true;
          if (chunk.tool_calls && chunk.tool_calls.length > 0) {
            collectedTools = [...collectedTools, ...chunk.tool_calls];
          }
          if (chunk.content) {
            streamedContent += chunk.content;
          }

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantId
                ? {
                    ...msg,
                    content: streamedContent,
                    toolCalls: collectedTools,
                    isStreaming: !chunk.done,
                  }
                : msg
            )
          );
        }
      } catch (streamErr) {
        // Fallback to non-streaming POST if stream failed or not supported in environment
        if (!streamSucceeded) {
          const resp = await api.ai.chat({
            messages: apiMessages,
            shg_id: activeShgId || undefined,
          });

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantId
                ? {
                    ...msg,
                    content: resp.content,
                    toolCalls: resp.tool_calls,
                    isStreaming: false,
                  }
                : msg
            )
          );
        } else {
          throw streamErr;
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof ApiException ? err.message : 'Failed to reach AI assistant.';
      setError(msg);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: 'Sorry, I encountered an issue while processing your request. Please try again.',
                isStreaming: false,
              }
            : m
        )
      );
    } finally {
      setIsLoading(false);
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
      );
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = () => {
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content:
          'Conversation reset. Ask me about member savings, loan portfolios, PAR metrics, or collection sheets.',
      },
    ]);
    setError(null);
  };

  const quickQuestions = [
    'What is our total corpus and savings?',
    'Show me delinquent and overdue loans',
    'What are the PAR 30 and PAR 90 figures?',
    'Check collection sheet dues for the next meeting',
  ];

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40 backdrop-blur-[1px] transition-opacity"
      aria-modal="true"
      role="dialog"
      aria-label="AI Financial Assistant"
    >
      {/* Background click to close */}
      <div className="flex-1" onClick={closeAssistant} />

      {/* Drawer Container */}
      <div className="w-full sm:w-[440px] md:w-[480px] bg-[var(--surface)] text-[var(--ink)] h-full flex flex-col shadow-2xl border-l border-[var(--border)] animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 border-b border-[var(--border)] flex items-center justify-between bg-[var(--surface-sunken)]">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-[var(--primary)] text-white flex items-center justify-center shadow-sm">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold tracking-tight text-[var(--ink)]">SHG AI Assistant</h2>
              <p className="text-[10px] text-[var(--muted-ink)] font-mono">
                Read-Only Tools &bull; Double-Entry Bounded
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClear}
              title="Clear conversation"
              aria-label="Clear conversation"
              className="h-8 w-8 p-0 text-[var(--muted-ink)]"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={closeAssistant}
              title="Close drawer"
              aria-label="Close drawer"
              className="h-8 w-8 p-0 text-[var(--muted-ink)]"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Disclaimer Banner */}
        <div className="px-3 py-2 bg-[var(--surface)] border-b border-[var(--border)] text-[11px] text-[var(--muted-ink)] flex items-start gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
          <span>
            <strong>AI Disclaimer:</strong> Responses are generated for informational assistance and may contain inaccuracies. Official double-entry ledger balances are authoritative.
          </span>
        </div>

        {/* Messages Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((m) => (
            <div
              key={m.id}
              className={`flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-[88%] rounded-lg px-3.5 py-2.5 text-xs leading-relaxed ${
                  m.role === 'user'
                    ? 'bg-[var(--primary)] text-white shadow-sm'
                    : 'bg-[var(--surface-sunken)] text-[var(--ink)] border border-[var(--border)]'
                }`}
              >
                {/* Collapsible tool calls list */}
                {m.toolCalls && m.toolCalls.length > 0 && (
                  <div className="mb-2 space-y-1.5 border-b border-[var(--border)]/70 pb-2">
                    <div className="text-[10px] font-semibold text-[var(--muted-ink)] uppercase tracking-wider flex items-center gap-1">
                      <Wrench className="w-3 h-3 text-[var(--primary)]" />
                      Tools Executed ({m.toolCalls.length})
                    </div>
                    {m.toolCalls.map((tc, idx) => (
                      <details
                        key={idx}
                        className="group bg-[var(--surface)] rounded border border-[var(--border)] text-[11px] overflow-hidden"
                      >
                        <summary className="flex items-center justify-between px-2 py-1.5 cursor-pointer select-none hover:bg-[var(--surface-sunken)]">
                          <span className="font-mono text-[10px] font-medium text-[var(--primary)] flex items-center gap-1">
                            <ChevronRight className="w-3 h-3 group-open:rotate-90 transition-transform" />
                            {tc.name}
                          </span>
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 font-medium">
                            read-only
                          </span>
                        </summary>
                        <div className="px-2.5 py-2 border-t border-[var(--border)] bg-[var(--surface-sunken)] font-mono text-[10px] space-y-1 text-[var(--muted-ink)]">
                          <div>
                            <span className="text-[var(--ink)] font-semibold">Args:</span>{' '}
                            {JSON.stringify(tc.arguments)}
                          </div>
                          <div>
                            <span className="text-[var(--ink)] font-semibold">Summary:</span>{' '}
                            <span className="text-[var(--ink)]">{tc.result_summary}</span>
                          </div>
                        </div>
                      </details>
                    ))}
                  </div>
                )}

                {/* Message Content */}
                <div className="whitespace-pre-wrap">{m.content}</div>

                {m.isStreaming && (
                  <span className="inline-block w-1.5 h-3 ml-1 bg-current animate-pulse" />
                )}
              </div>
            </div>
          ))}

          {/* Error Banner */}
          {error && (
            <div className="p-3 rounded border border-danger/30 bg-danger/10 text-danger text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggestion Chips */}
        {messages.length <= 2 && (
          <div className="px-4 py-2 border-t border-[var(--border)] bg-[var(--surface)]">
            <div className="text-[10px] font-medium text-[var(--muted-ink)] mb-1.5 flex items-center gap-1">
              <HelpCircle className="w-3 h-3" /> Quick queries:
            </div>
            <div className="flex flex-wrap gap-1.5">
              {quickQuestions.map((q, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSend(q)}
                  className="text-[11px] text-left px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface-sunken)] text-[var(--ink)] hover:border-[var(--primary)] hover:text-[var(--primary)] transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input Footer */}
        <div className="p-3 border-t border-[var(--border)] bg-[var(--surface)]">
          <div className="relative flex items-center">
            <textarea
              ref={inputRef}
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask financial questions or request statements... (Enter to send)"
              className="w-full resize-none rounded-md border border-[var(--border)] bg-[var(--surface-sunken)] px-3 py-2 pr-10 text-xs text-[var(--ink)] placeholder:text-[var(--muted-ink)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
              disabled={isLoading}
            />
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={() => handleSend()}
              disabled={!input.trim() || isLoading}
              className="absolute right-2 bottom-2 h-7 w-7 p-0 flex items-center justify-center rounded"
              title="Send Message"
              aria-label="Send Message"
            >
              <Send className="w-3.5 h-3.5" />
            </Button>
          </div>
          <div className="mt-1 flex justify-between items-center text-[10px] text-[var(--muted-ink)] px-1">
            <span>Shift + Enter for new line</span>
            <span className="flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Safe LLM: Ledger writes blocked
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
