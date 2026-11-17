import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemberAttendanceTab } from '../src/features/members/MemberAttendanceTab';
import { api } from '../src/lib/api/client';
import type { MemberAttendanceResponse } from '../src/lib/api/types';

vi.mock('../src/lib/api/client', async () => {
  const actual = await vi.importActual<typeof import('../src/lib/api/client')>('../src/lib/api/client');
  return {
    ...actual,
    api: {
      ...actual.api,
      meetings: {
        ...actual.api.meetings,
        getMemberAttendance: vi.fn(),
      },
    },
  };
});

describe('Member Profile: Attendance Tab', () => {
  let queryClient: QueryClient;

  const mockAttendanceData: MemberAttendanceResponse = {
    member_id: 'mem-123',
    member_name: 'Radha Devi',
    summary: {
      total_meetings: 10,
      present_count: 9,
      absent_count: 1,
      excused_count: 0,
      attendance_rate: '90.0%',
    },
    records: [
      {
        meeting_id: 'meet-1',
        meeting_date: '2026-03-15',
        agenda: 'Monthly savings & loan review',
        status: 'PRESENT',
        recorded_at: '2026-03-15T10:00:00Z',
      },
      {
        meeting_id: 'meet-2',
        meeting_date: '2026-02-15',
        agenda: 'February assembly',
        status: 'ABSENT',
        recorded_at: '2026-02-15T10:00:00Z',
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    vi.mocked(api.meetings.getMemberAttendance).mockResolvedValue(mockAttendanceData);
  });

  it('renders attendance metrics summary banner and meeting register', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemberAttendanceTab memberId="mem-123" />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('90.0%')).toBeInTheDocument();
      expect(screen.getByText('10')).toBeInTheDocument();
      expect(screen.getByText('9')).toBeInTheDocument();
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    // Verify register rows
    expect(screen.getByText('2026-03-15')).toBeInTheDocument();
    expect(screen.getByText('2026-02-15')).toBeInTheDocument();
    expect(screen.getByText(/\[PRESENT\]/)).toBeInTheDocument();
    expect(screen.getByText(/\[ABSENT\]/)).toBeInTheDocument();
  });
});
