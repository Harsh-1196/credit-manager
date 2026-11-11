import type {
  ApiError,
  ChangePasswordRequest,
  GroupCreateRequest,
  GroupResponse,
  GroupSettingsResponse,
  GroupSettingsUpdateRequest,
  GroupUpdateRequest,
  JournalEntryResponse,
  JournalEntryReverseRequest,
  LedgerReportResponse,
  LoanApproveRequest,
  LoanCreateRequest,
  LoanDetailResponse,
  LoanDisbursePreviewResponse,
  LoanDisburseRequest,
  LoanPreviewScheduleRequest,
  LoanPreviewScheduleResponse,
  LoanRejectRequest,
  LoanRepayPreviewRequest,
  LoanRepayPreviewResponse,
  LoanRepayRequest,
  LoanResponse,
  LoanStatusHistoryResponse,
  LoanWriteOffRequest,
  PortfolioMetricsResponse,
  LoginRequest,
  LoginResponse,
  MeResponse,
  MeetingDetailResponse,
  MeetingResponse,
  MemberCreateRequest,
  MemberExitRequest,
  MemberPassbookResponse,
  MemberResponse,
  MemberUpdateRequest,
  PaginatedResult,
  SavingsCollectRequest,
  SavingsCollectResponse,
  SavingsDueResponse,
  SavingsWithdrawRequest,
  SavingsWithdrawResponse,
  UserCreateRequest,
  UserResponse,
  UserUpdateRequest,
} from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

let currentAccessToken: string | null = null;
let currentCsrfToken: string | null = null;
let onUnauthorizedHandler: (() => void) | null = null;
let refreshPromise: Promise<string | null> | null = null;

function getCsrfFromCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(^|;\\s*)shg_csrf_token=([^;]*)'));
  return match ? decodeURIComponent(match[2]) : null;
}

export function setTokens(accessToken: string | null, csrfToken?: string | null): void {
  currentAccessToken = accessToken;
  if (csrfToken !== undefined) {
    currentCsrfToken = csrfToken;
  }
}

export function getAccessToken(): string | null {
  return currentAccessToken;
}

export function getCsrfToken(): string | null {
  return currentCsrfToken || getCsrfFromCookie();
}

export function setOnUnauthorized(handler: (() => void) | null): void {
  onUnauthorizedHandler = handler;
}

export class ApiException extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown> | null;
  readonly requestId?: string | null;

  constructor(status: number, errorData: ApiError) {
    super(errorData.message || 'An unexpected error occurred');
    this.name = 'ApiException';
    this.status = status;
    this.code = errorData.code || 'UNKNOWN_ERROR';
    this.details = errorData.details;
    this.requestId = errorData.request_id;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  isRetry = false
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (currentAccessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${currentAccessToken}`);
  }

  const method = (options.method || 'GET').toUpperCase();
  const csrf = getCsrfToken();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && csrf) {
    headers.set('X-CSRF-Token', csrf);
  }

  const fetchOptions: RequestInit = {
    ...options,
    headers,
    credentials: 'include', // Ensure cookies (refresh token) are sent
  };

  const response = await fetch(url, fetchOptions);

  if (response.status === 401 && !isRetry && !path.includes('/auth/login') && !path.includes('/auth/refresh')) {
    // Attempt silent token refresh
    try {
      if (!refreshPromise) {
        refreshPromise = (async () => {
          const refRes = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
          });

          if (!refRes.ok) {
            setTokens(null, null);
            if (onUnauthorizedHandler) {
              onUnauthorizedHandler();
            }
            return null;
          }

          const refData = (await refRes.json()) as LoginResponse;
          setTokens(refData.access_token);
          return refData.access_token;
        })().finally(() => {
          refreshPromise = null;
        });
      }

      const newToken = await refreshPromise;
      if (newToken) {
        return request<T>(path, options, true);
      }
    } catch {
      setTokens(null, null);
      if (onUnauthorizedHandler) {
        onUnauthorizedHandler();
      }
    }
  }

  if (!response.ok) {
    let errorData: ApiError;
    try {
      errorData = (await response.json()) as ApiError;
    } catch {
      errorData = {
        code: `HTTP_${response.status}`,
        message: response.statusText || 'Request failed',
      };
    }
    throw new ApiException(response.status, errorData);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  auth: {
    login: async (body: LoginRequest): Promise<LoginResponse> => {
      const data = await request<LoginResponse>('/auth/login', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setTokens(data.access_token);
      return data;
    },
    refresh: async (): Promise<LoginResponse> => {
      const data = await request<LoginResponse>('/auth/refresh', {
        method: 'POST',
      });
      setTokens(data.access_token);
      return data;
    },
    logout: async (): Promise<void> => {
      try {
        await request<void>('/auth/logout', { method: 'POST' });
      } finally {
        setTokens(null, null);
      }
    },
    me: async (): Promise<MeResponse> => {
      return request<MeResponse>('/auth/me');
    },
    changePassword: async (body: ChangePasswordRequest): Promise<void> => {
      await request<void>('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
  },

  groups: {
    list: async (params?: { page?: number; page_size?: number; status?: string }): Promise<PaginatedResult<GroupResponse>> => {
      const query = new URLSearchParams();
      if (params?.page) query.set('page', String(params.page));
      if (params?.page_size) query.set('page_size', String(params.page_size));
      if (params?.status) query.set('status', params.status);
      const qs = query.toString();
      return request<PaginatedResult<GroupResponse>>(`/groups${qs ? `?${qs}` : ''}`);
    },
    create: async (body: GroupCreateRequest): Promise<GroupResponse> => {
      return request<GroupResponse>('/groups', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    get: async (id: string): Promise<GroupResponse> => {
      return request<GroupResponse>(`/groups/${id}`);
    },
    update: async (id: string, body: GroupUpdateRequest): Promise<GroupResponse> => {
      return request<GroupResponse>(`/groups/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
    },
    getSettings: async (groupId: string): Promise<GroupSettingsResponse> => {
      return request<GroupSettingsResponse>(`/groups/${groupId}/settings`);
    },
    updateSettings: async (groupId: string, body: GroupSettingsUpdateRequest): Promise<GroupSettingsResponse> => {
      return request<GroupSettingsResponse>(`/groups/${groupId}/settings`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
    },
  },

  members: {
    listByGroup: async (
      groupId: string,
      params?: { page?: number; page_size?: number; status?: string; query?: string }
    ): Promise<PaginatedResult<MemberResponse>> => {
      const sp = new URLSearchParams();
      if (params?.page) sp.set('page', String(params.page));
      if (params?.page_size) sp.set('page_size', String(params.page_size));
      if (params?.status) sp.set('status', params.status);
      if (params?.query) sp.set('query', params.query);
      const qs = sp.toString();
      return request<PaginatedResult<MemberResponse>>(`/groups/${groupId}/members${qs ? `?${qs}` : ''}`);
    },
    create: async (groupId: string, body: MemberCreateRequest): Promise<MemberResponse> => {
      return request<MemberResponse>(`/groups/${groupId}/members`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    get: async (id: string): Promise<MemberResponse> => {
      return request<MemberResponse>(`/members/${id}`);
    },
    update: async (id: string, body: MemberUpdateRequest): Promise<MemberResponse> => {
      return request<MemberResponse>(`/members/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
    },
    exit: async (id: string, body: MemberExitRequest): Promise<MemberResponse> => {
      return request<MemberResponse>(`/members/${id}/exit`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
  },

  users: {
    list: async (params?: { page?: number; page_size?: number }): Promise<PaginatedResult<UserResponse>> => {
      const sp = new URLSearchParams();
      if (params?.page) sp.set('page', String(params.page));
      if (params?.page_size) sp.set('page_size', String(params.page_size));
      const qs = sp.toString();
      return request<PaginatedResult<UserResponse>>(`/users${qs ? `?${qs}` : ''}`);
    },
    create: async (body: UserCreateRequest): Promise<UserResponse> => {
      return request<UserResponse>('/users', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    get: async (id: string): Promise<UserResponse> => {
      return request<UserResponse>(`/users/${id}`);
    },
    update: async (id: string, body: UserUpdateRequest): Promise<UserResponse> => {
      return request<UserResponse>(`/users/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      });
    },
    deactivate: async (id: string): Promise<void> => {
      await request<void>(`/users/${id}`, { method: 'DELETE' });
    },
  },

  ledger: {
    getMemberPassbook: async (memberId: string, fromDate?: string, toDate?: string): Promise<MemberPassbookResponse> => {
      const sp = new URLSearchParams();
      if (fromDate) sp.set('from_date', fromDate);
      if (toDate) sp.set('to_date', toDate);
      const qs = sp.toString();
      return request<MemberPassbookResponse>(`/members/${memberId}/passbook${qs ? `?${qs}` : ''}`);
    },
    reverseEntry: async (entryId: string, body: JournalEntryReverseRequest): Promise<JournalEntryResponse> => {
      return request<JournalEntryResponse>(`/ledger/entries/${entryId}/reverse`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    getGroupLedger: async (groupId: string): Promise<LedgerReportResponse> => {
      return request<LedgerReportResponse>(`/groups/${groupId}/ledger`);
    },
  },

  savings: {
    getMemberSavings: async (memberId: string): Promise<{
      member_id: string;
      member_name: string;
      shg_id: string;
      total_savings_balance: string;
      dues: Array<{
        id: string;
        period: string;
        amount_due: string;
        amount_paid: string;
        status: string;
      }>;
    }> => {
      return request(`/members/${memberId}/savings`);
    },
    getGroupSavingsDues: async (groupId: string, period?: string): Promise<SavingsDueResponse[]> => {
      const sp = new URLSearchParams();
      if (period) sp.set('period', period);
      const qs = sp.toString();
      return request<SavingsDueResponse[]>(`/groups/${groupId}/savings-dues${qs ? `?${qs}` : ''}`);
    },
    generateSavingsDues: async (groupId: string, period: string): Promise<SavingsDueResponse[]> => {
      return request<SavingsDueResponse[]>(`/groups/${groupId}/savings-dues/generate`, {
        method: 'POST',
        body: JSON.stringify({ period }),
      });
    },
    collect: async (body: SavingsCollectRequest, idempotencyKey?: string): Promise<SavingsCollectResponse> => {
      const headers: Record<string, string> = {};
      if (idempotencyKey) {
        headers['Idempotency-Key'] = idempotencyKey;
      }
      return request<SavingsCollectResponse>('/savings/collect', {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
    },
    withdraw: async (body: SavingsWithdrawRequest, idempotencyKey?: string): Promise<SavingsWithdrawResponse> => {
      const headers: Record<string, string> = {};
      if (idempotencyKey) {
        headers['Idempotency-Key'] = idempotencyKey;
      }
      return request<SavingsWithdrawResponse>('/savings/withdraw', {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
    },
  },

  meetings: {
    list: async (groupId: string): Promise<MeetingResponse[]> => {
      return request<MeetingResponse[]>(`/groups/${groupId}/meetings`);
    },
    get: async (meetingId: string): Promise<MeetingDetailResponse> => {
      return request<MeetingDetailResponse>(`/meetings/${meetingId}`);
    },
  },

  loans: {
    previewSchedule: async (body: LoanPreviewScheduleRequest): Promise<LoanPreviewScheduleResponse> => {
      return request<LoanPreviewScheduleResponse>('/loans/preview-schedule', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    create: async (body: LoanCreateRequest): Promise<LoanResponse> => {
      return request<LoanResponse>('/loans', {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    list: async (params?: { group_id?: string; member_id?: string; status?: string }): Promise<LoanResponse[]> => {
      const sp = new URLSearchParams();
      if (params?.group_id) sp.set('group_id', params.group_id);
      if (params?.member_id) sp.set('member_id', params.member_id);
      if (params?.status) sp.set('status', params.status);
      const qs = sp.toString();
      return request<LoanResponse[]>(`/loans${qs ? `?${qs}` : ''}`);
    },
    get: async (id: string): Promise<LoanDetailResponse> => {
      return request<LoanDetailResponse>(`/loans/${id}`);
    },
    submit: async (id: string): Promise<LoanResponse> => {
      return request<LoanResponse>(`/loans/${id}/submit`, {
        method: 'POST',
      });
    },
    approve: async (id: string, body: LoanApproveRequest): Promise<LoanResponse> => {
      return request<LoanResponse>(`/loans/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    reject: async (id: string, body: LoanRejectRequest): Promise<LoanResponse> => {
      return request<LoanResponse>(`/loans/${id}/reject`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    history: async (id: string): Promise<LoanStatusHistoryResponse[]> => {
      return request<LoanStatusHistoryResponse[]>(`/loans/${id}/history`);
    },
    getDisbursePreview: async (id: string): Promise<LoanDisbursePreviewResponse> => {
      return request<LoanDisbursePreviewResponse>(`/loans/${id}/disburse-preview`);
    },
    disburse: async (id: string, body: LoanDisburseRequest, idempotencyKey?: string): Promise<LoanResponse> => {
      const headers: Record<string, string> = {};
      if (idempotencyKey) {
        headers['Idempotency-Key'] = idempotencyKey;
      }
      return request<LoanResponse>(`/loans/${id}/disburse`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
    },
    previewRepayment: async (id: string, body: LoanRepayPreviewRequest): Promise<LoanRepayPreviewResponse> => {
      return request<LoanRepayPreviewResponse>(`/loans/${id}/preview-repayment`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    repay: async (id: string, body: LoanRepayRequest, idempotencyKey?: string): Promise<LoanDetailResponse> => {
      const headers: Record<string, string> = {};
      if (idempotencyKey) {
        headers['Idempotency-Key'] = idempotencyKey;
      }
      return request<LoanDetailResponse>(`/loans/${id}/repay`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
    },
    writeOff: async (id: string, body: LoanWriteOffRequest): Promise<LoanResponse> => {
      return request<LoanResponse>(`/loans/${id}/write-off`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
    },
    getPortfolioMetrics: async (params?: { shg_id?: string; as_of_date?: string }): Promise<PortfolioMetricsResponse> => {
      const sp = new URLSearchParams();
      if (params?.shg_id) sp.set('shg_id', params.shg_id);
      if (params?.as_of_date) sp.set('as_of_date', params.as_of_date);
      const qs = sp.toString();
      return request<PortfolioMetricsResponse>(`/loans/metrics/portfolio${qs ? `?${qs}` : ''}`);
    },
  },
};
