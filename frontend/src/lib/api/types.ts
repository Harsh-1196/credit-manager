import type { components } from './schema';

export type UserRole = components['schemas']['UserRole'];
export type UserResponse = components['schemas']['UserSummaryResponse'];
export type UserCreateRequest = components['schemas']['UserCreateRequest'];
export type UserUpdateRequest = components['schemas']['UserUpdateRequest'];
export type MeResponse = components['schemas']['UserDetailResponse'];
export type LoginRequest = components['schemas']['LoginRequest'];
export type LoginResponse = components['schemas']['TokenResponse'];
export type ChangePasswordRequest = components['schemas']['ChangePasswordRequest'];

export type GroupResponse = components['schemas']['SHGResponse'];
export type GroupCreateRequest = components['schemas']['SHGCreateRequest'];
export type GroupUpdateRequest = components['schemas']['SHGUpdateRequest'];
export type GroupSettingsResponse = components['schemas']['GroupSettingsResponse'];
export type GroupSettingsUpdateRequest = components['schemas']['GroupSettingsUpdateRequest'];
export type SHGStatus = components['schemas']['SHGStatus'];
export type InterestType = components['schemas']['InterestType'];

export type MemberResponse = components['schemas']['MemberResponse'];
export type MemberCreateRequest = components['schemas']['MemberCreateRequest'];
export type MemberUpdateRequest = components['schemas']['MemberUpdateRequest'];
export type MemberExitRequest = components['schemas']['MemberExitRequest'];
export type MemberStatus = components['schemas']['MemberStatus'];
export type OfficeBearerRole = components['schemas']['OfficeBearerRole'];

// Phase 2: Ledger & Passbook
export type PassbookEntry = components['schemas']['PassbookEntryResponse'];
export type MemberPassbookResponse = components['schemas']['MemberPassbookResponse'];
export type JournalEntryResponse = components['schemas']['JournalEntryResponse'];
export type JournalEntryReverseRequest = components['schemas']['JournalEntryReverseRequest'];
export type LedgerReportResponse = components['schemas']['LedgerReportResponse'];
export type TrialBalanceItem = components['schemas']['TrialBalanceItem'];

// Phase 2: Savings
export type SavingsDueResponse = components['schemas']['SavingsDueResponse'];
export type SavingsDueStatus = components['schemas']['SavingsDueStatus'];
export type SavingsCollectRequest = components['schemas']['SavingsCollectRequest'];
export type SavingsCollectResponse = components['schemas']['SavingsCollectResponse'];
export type SavingsWithdrawRequest = components['schemas']['SavingsWithdrawRequest'];
export type SavingsWithdrawResponse = components['schemas']['SavingsWithdrawResponse'];

// Phase 2: Meetings & Attendance
export type MeetingResponse = components['schemas']['MeetingResponse'];
export type MeetingDetailResponse = components['schemas']['MeetingDetailResponse'];
export type MeetingStatus = components['schemas']['MeetingStatus'];
export type AttendanceRecord = components['schemas']['AttendanceRecord'];
export type AttendanceStatus = components['schemas']['AttendanceStatus'];

// Phase 3a & 3b: Loans
export type LoanResponse = components['schemas']['LoanResponse'];
export type LoanDetailResponse = components['schemas']['LoanDetailResponse'];
export type LoanStatus = components['schemas']['LoanStatus'];
export type LoanScheduleStatus = components['schemas']['LoanScheduleStatus'];
export type LoanScheduleItemResponse = components['schemas']['LoanScheduleItemResponse'];
export type LoanCreateRequest = components['schemas']['LoanCreateRequest'];
export type LoanApproveRequest = components['schemas']['LoanApproveRequest'];
export type LoanRejectRequest = components['schemas']['LoanRejectRequest'];
export type LoanPreviewScheduleRequest = components['schemas']['LoanPreviewScheduleRequest'];
export type LoanPreviewScheduleResponse = components['schemas']['LoanPreviewScheduleResponse'];
export type LoanStatusHistoryResponse = components['schemas']['LoanStatusHistoryResponse'];
export type EligibilityResponse = components['schemas']['EligibilityResponse'];
export type EligibilityCheckItemResponse = components['schemas']['EligibilityCheckItemResponse'];

// Phase 3b: Money movement, disbursal, repayment, portfolio
export type LoanDisburseRequest = components['schemas']['LoanDisburseRequest'];
export type LoanDisbursePreviewResponse = components['schemas']['LoanDisbursePreviewResponse'];
export type LoanRepayRequest = components['schemas']['LoanRepayRequest'];
export type LoanRepayPreviewRequest = components['schemas']['LoanRepayPreviewRequest'];
export type LoanRepayPreviewResponse = components['schemas']['LoanRepayPreviewResponse'];
export type LoanWriteOffRequest = components['schemas']['LoanWriteOffRequest'];
export type LoanSummaryFiguresResponse = components['schemas']['LoanSummaryFiguresResponse'];
export type PortfolioMetricsResponse = components['schemas']['PortfolioMetricsResponse'];

export interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
  request_id?: string | null;
}
