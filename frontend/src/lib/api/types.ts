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
