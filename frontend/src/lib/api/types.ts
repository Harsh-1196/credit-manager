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

// Phase 2 & 4: Meetings & Attendance & Collections
export type MeetingResponse = components['schemas']['MeetingResponse'];
export type MeetingDetailResponse = components['schemas']['MeetingDetailResponse'];
export type MeetingStatus = components['schemas']['MeetingStatus'];
export type AttendanceRecord = components['schemas']['AttendanceRecord'];
export type AttendanceStatus = components['schemas']['AttendanceStatus'];
export type CollectionSheetResponse = components['schemas']['CollectionSheetResponse'];
export type CollectionSheetMemberRow = components['schemas']['CollectionSheetMemberRow'];
export type CollectionSheetTotals = components['schemas']['CollectionSheetTotals'];
export type MeetingBatchCollectionsRequest = components['schemas']['MeetingBatchCollectionsRequest'];
export type MeetingBatchCollectionItem = components['schemas']['MeetingBatchCollectionItem'];
export type MeetingBatchCollectionsResponse = components['schemas']['MeetingBatchCollectionsResponse'];
export type MemberAttendanceResponse = components['schemas']['MemberAttendanceResponse'];
export type MemberAttendanceRecord = components['schemas']['MemberAttendanceRecord'];
export type MemberAttendanceSummary = components['schemas']['MemberAttendanceSummary'];

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

// Phase 5: Audit, Reconciliation & System Status
export type AuditLogListResponse = components['schemas']['AuditLogListResponse'];
export type AuditLogRowResponse = components['schemas']['AuditLogRowResponse'];
export type AuditVerificationResponse = components['schemas']['AuditVerificationResponse'];
export type ReconciliationRunResponse = components['schemas']['ReconciliationRunResponse'];
export type WorkerStatusResponse = components['schemas']['WorkerStatusResponse'];

// Phase 6a: Dashboard & Reports
export type DashboardResponse = components['schemas']['DashboardResponse'];
export type GroupDashboardReportResponse = components['schemas']['GroupDashboardReportResponse'];
export type AgingBucketItem = components['schemas']['AgingBucketItem'];
export type SavingsTrendItem = components['schemas']['SavingsTrendItem'];
export type DisbursalVsRepaymentItem = components['schemas']['DisbursalVsRepaymentItem'];
export type CollectionDueItem = components['schemas']['CollectionDueItem'];

export interface TrialBalanceReportItem {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: string;
  debit_balance: string;
  credit_balance: string;
}

export interface JournalEntryReportItem {
  entry_id: string;
  entry_date: string;
  description: string;
  source_type: string;
  lines: Array<{
    line_id: string;
    account_code: string;
    account_name: string;
    debit: string;
    credit: string;
  }>;
}

export interface GroupLedgerReportResponse {
  shg_id: string;
  shg_name: string;
  as_of_date: string;
  trial_balance: TrialBalanceReportItem[];
  journal_entries: JournalEntryReportItem[];
}

export interface LoanPortfolioItem {
  loan_id: string;
  loan_number: string;
  borrower_name: string;
  principal: string;
  outstanding_principal: string;
  overdue_principal: string;
  days_overdue: number;
  aging_bucket: string;
  status: string;
}

export interface LoanPortfolioReportResponse {
  shg_id: string;
  shg_name: string;
  as_of_date: string;
  active_loans_count: number;
  total_disbursed_principal: string;
  total_outstanding_principal: string;
  total_overdue_principal: string;
  par_30: string;
  par_60: string;
  par_90: string;
  aging_buckets: AgingBucketItem[];
  loans: LoanPortfolioItem[];
}

export interface PassbookLedgerItem {
  entry_id: string;
  date: string;
  particulars: string;
  source_type: string;
  debit: string;
  credit: string;
  balance: string;
}

export interface MemberStatementSummary {
  member_id: string;
  name: string;
  phone: string | null;
  shg_name: string;
  status: string;
  joined_on: string;
  total_savings_balance: string;
  total_loan_outstanding: string;
}

export interface MemberStatementReportResponse {
  member: MemberStatementSummary;
  passbook_entries: PassbookLedgerItem[];
  active_loans: Array<{
    loan_id: string;
    loan_number: string;
    principal: string;
    outstanding_principal: string;
    interest_rate: string;
    status: string;
  }>;
  attendance_summary?: {
    total_meetings: number;
    present: number;
    absent: number;
    percentage: number;
  } | null;
}

export interface AuditLogFilters {
  actor_id?: string;
  entity_type?: string;
  action?: string;
  from_date?: string;
  to_date?: string;
  limit?: number;
  offset?: number;
}

export interface DiscrepancyItem {
  shg_id: string;
  shg_name?: string;
  entity_type: string;
  entity_id: string;
  member_name?: string;
  ledger_value: string;
  domain_value: string;
  difference: string;
  explanation: string;
}

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

// Phase 6b: AI Assistant & Draft Collection
export interface ToolCallRecord {
  name: string;
  arguments: Record<string, unknown>;
  result_summary: string;
}

export interface ChatResponse {
  role: string;
  content: string;
  tool_calls: ToolCallRecord[];
  shg_id?: string | null;
}

export type ChatMessage = components['schemas']['ChatMessage'];
export type ChatRequest = components['schemas']['ChatRequest'];
export type DraftCollectionRequest = components['schemas']['DraftCollectionRequest'];
export type DraftCollectionResponse = components['schemas']['DraftCollectionResponse'];
export type DraftMemberAmount = components['schemas']['DraftMemberAmount'];
export type UnmatchedNoteItem = components['schemas']['UnmatchedNoteItem'];

