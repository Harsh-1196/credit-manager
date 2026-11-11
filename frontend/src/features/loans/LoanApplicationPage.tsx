import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useQuery } from '@tanstack/react-query';
import { api, ApiException } from '../../lib/api/client';
import type {
  GroupResponse,
  MemberResponse,
  LoanPreviewScheduleResponse,
  InterestType,
} from '../../lib/api/types';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { MoneyText } from '../../components/ui/MoneyText';
import { Skeleton } from '../../components/ui/Skeleton';
import {
  AlertCircle,
  CreditCard,
  FileText,
  Calculator,
} from 'lucide-react';

const loanApplicationSchema = z.object({
  group_id: z.string().min(1, 'Please select a Self-Help Group'),
  member_id: z.string().min(1, 'Please select a member applicant'),
  principal: z.string().refine((val) => {
    const num = Number(val);
    return !isNaN(num) && num > 0;
  }, 'Principal must be greater than zero'),
  interest_rate: z.string().refine((val) => {
    const num = Number(val);
    return !isNaN(num) && num >= 0;
  }, 'Interest rate must be 0% or positive'),
  interest_type: z.enum(['REDUCING', 'FLAT'] as const),
  tenure_months: z.string().refine((val) => {
    const num = Number(val);
    return !isNaN(num) && Number.isInteger(num) && num >= 1 && num <= 120;
  }, 'Tenure must be between 1 and 120 months'),
  purpose: z.string().min(3, 'Purpose must be at least 3 characters'),
  first_due_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Valid YYYY-MM-DD date required'),
});

type LoanApplicationFormData = z.infer<typeof loanApplicationSchema>;

function getDefaultFirstDueDate(): string {
  const d = new Date();
  d.setMonth(d.getMonth() + 1);
  return d.toISOString().split('T')[0];
}

export const LoanApplicationPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const preselectedGroupId = searchParams.get('group_id') || '';
  const preselectedMemberId = searchParams.get('member_id') || '';

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitMode, setSubmitMode] = useState<'submit' | 'draft'>('submit');
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    control,
    formState: { errors },
  } = useForm<LoanApplicationFormData>({
    resolver: zodResolver(loanApplicationSchema),
    defaultValues: {
      group_id: preselectedGroupId,
      member_id: preselectedMemberId,
      principal: '10000.00',
      interest_rate: '12.00',
      interest_type: 'REDUCING',
      tenure_months: '12',
      purpose: '',
      first_due_date: getDefaultFirstDueDate(),
    },
  });

  const selectedGroupId = watch('group_id');
  const selectedMemberId = watch('member_id');
  const principalVal = watch('principal');
  const interestRateVal = watch('interest_rate');
  const interestTypeVal = watch('interest_type');
  const tenureVal = watch('tenure_months');
  const firstDueDateVal = watch('first_due_date');

  // Load groups for selector
  const { data: groupsData, isLoading: groupsLoading } = useQuery({
    queryKey: ['groups', 'list'],
    queryFn: () => api.groups.list({ page_size: 100, status: 'ACTIVE' }),
  });

  // Load group settings when group changes to prefill rate & multiple
  const { data: groupSettings } = useQuery({
    queryKey: ['group-settings', selectedGroupId],
    queryFn: () => api.groups.getSettings(selectedGroupId),
    enabled: !!selectedGroupId,
  });

  // Update interest defaults when settings load
  useEffect(() => {
    if (groupSettings) {
      if (groupSettings.default_interest_rate) {
        setValue('interest_rate', String(groupSettings.default_interest_rate));
      }
      if (groupSettings.interest_type) {
        setValue('interest_type', groupSettings.interest_type as InterestType);
      }
    }
  }, [groupSettings, setValue]);

  // Load members for selected group
  const { data: membersData, isLoading: membersLoading } = useQuery({
    queryKey: ['members', selectedGroupId],
    queryFn: () => api.members.listByGroup(selectedGroupId, { page_size: 100, status: 'ACTIVE' }),
    enabled: !!selectedGroupId,
  });

  // Debounced schedule & eligibility preview state
  const [debouncedParams, setDebouncedParams] = useState<{
    groupId: string;
    memberId: string;
    principal: string;
    rate: string;
    type: InterestType;
    tenure: string;
    dueDate: string;
  } | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (
        selectedGroupId &&
        Number(principalVal) > 0 &&
        Number(tenureVal) >= 1 &&
        /^\d{4}-\d{2}-\d{2}$/.test(firstDueDateVal)
      ) {
        setDebouncedParams({
          groupId: selectedGroupId,
          memberId: selectedMemberId,
          principal: principalVal,
          rate: interestRateVal || '0',
          type: interestTypeVal as InterestType,
          tenure: tenureVal,
          dueDate: firstDueDateVal,
        });
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [
    selectedGroupId,
    selectedMemberId,
    principalVal,
    interestRateVal,
    interestTypeVal,
    tenureVal,
    firstDueDateVal,
  ]);

  // Live schedule preview query
  const {
    data: previewData,
    isLoading: isPreviewLoading,
    isFetching: isPreviewFetching,
  } = useQuery<LoanPreviewScheduleResponse, ApiException>({
    queryKey: ['loans', 'preview', debouncedParams],
    queryFn: async () => {
      if (!debouncedParams) throw new Error('Params missing');
      return api.loans.previewSchedule({
        shg_id: debouncedParams.groupId,
        member_id: debouncedParams.memberId || undefined,
        principal: debouncedParams.principal,
        annual_rate: debouncedParams.rate,
        interest_type: debouncedParams.type,
        tenure_months: Number(debouncedParams.tenure),
        first_due_date: debouncedParams.dueDate,
      });
    },
    enabled: !!debouncedParams,
    retry: false,
  });

  // Calculate blockers
  const blockerChecks = useMemo(() => {
    if (!previewData?.eligibility?.checks) return [];
    return previewData.eligibility.checks.filter((c) => c.severity === 'BLOCKER' && !c.passed);
  }, [previewData]);

  const hasBlockers = blockerChecks.length > 0;

  const onSubmit = async (data: LoanApplicationFormData) => {
    setIsSubmitting(true);
    setApiError(null);
    try {
      const createdLoan = await api.loans.create({
        shg_id: data.group_id,
        member_id: data.member_id,
        principal: data.principal,
        interest_rate: data.interest_rate,
        interest_type: data.interest_type,
        tenure_months: Number(data.tenure_months),
        purpose: data.purpose,
        first_due_date: data.first_due_date,
        submit_immediately: submitMode === 'submit',
      });

      if (submitMode === 'submit') {
        navigate(`/loans/${createdLoan.id}?submitted=true`);
      } else {
        navigate(`/loans/${createdLoan.id}?saved=true`);
      }
    } catch (err: unknown) {
      if (err instanceof ApiException) {
        setApiError(err.message || 'Failed to submit loan application.');
      } else {
        setApiError('An unexpected network error occurred.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Editorial Header */}
      <div className="border-b border-[var(--border)] pb-4">
        <h1 className="font-serif text-2xl font-bold tracking-tight text-[var(--ink)]">
          Screen 7: Loan Application
        </h1>
        <p className="mt-1 text-sm text-[var(--muted-ink)]">
          Create and evaluate a loan proposal with automated double-entry schedule generation and
          live group credit eligibility checks.
        </p>
      </div>

      {apiError && (
        <div className="p-4 rounded border border-danger/30 bg-surface-sunken flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-danger shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold text-danger">Application Submission Error</h4>
            <p className="text-xs text-[var(--ink)] mt-1">{apiError}</p>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit(onSubmit)}>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Loan Application Inputs */}
          <div className="lg:col-span-5 space-y-6">
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded p-5 space-y-4 shadow-sm">
              <div className="flex items-center gap-2 border-b border-[var(--border)] pb-3">
                <FileText className="w-4 h-4 text-[var(--primary)]" />
                <h2 className="font-serif text-base font-semibold text-[var(--ink)]">
                  Application Particulars
                </h2>
              </div>

              {/* Group Select */}
              <div>
                <Controller
                  control={control}
                  name="group_id"
                  render={({ field }) => (
                    <Select
                      {...field}
                      label="Self-Help Group *"
                      disabled={groupsLoading}
                      options={[
                        { label: '-- Select Group --', value: '' },
                        ...(groupsData?.items.map((g: GroupResponse) => ({
                          label: `${g.name} (${g.district})`,
                          value: g.id,
                        })) || []),
                      ]}
                      error={errors.group_id?.message}
                    />
                  )}
                />
              </div>

              {/* Member Select */}
              <div>
                <Controller
                  control={control}
                  name="member_id"
                  render={({ field }) => (
                    <Select
                      {...field}
                      label="Applicant Member *"
                      disabled={!selectedGroupId || membersLoading}
                      options={[
                        {
                          label: selectedGroupId
                            ? membersLoading
                              ? 'Loading members...'
                              : '-- Select Member --'
                            : 'First select a group',
                          value: '',
                        },
                        ...(membersData?.items.map((m: MemberResponse) => ({
                          label: `${m.full_name} (${m.phone || 'No phone'})`,
                          value: m.id,
                        })) || []),
                      ]}
                      error={errors.member_id?.message}
                    />
                  )}
                />
              </div>

              {/* Principal Amount */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                  Principal Amount (₹) *
                </label>
                <Input
                  {...register('principal')}
                  placeholder="50000.00"
                  error={errors.principal?.message}
                />
                <span className="text-[11px] text-[var(--muted-ink)] mt-0.5 block">
                  Numeric string, e.g. 10000.00 (quantized to 2 decimal places)
                </span>
              </div>

              {/* Interest Type & Annual Rate */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                    Interest Type *
                  </label>
                  <Controller
                    control={control}
                    name="interest_type"
                    render={({ field }) => (
                      <Select
                        {...field}
                        aria-label="Interest Type"
                        options={[
                          { label: 'Reducing (EMI)', value: 'REDUCING' },
                          { label: 'Flat Rate', value: 'FLAT' },
                        ]}
                      />
                    )}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                    Annual Rate (%) *
                  </label>
                  <Input
                    {...register('interest_rate')}
                    placeholder="12.00"
                    error={errors.interest_rate?.message}
                  />
                </div>
              </div>

              {/* Tenure & Due Date */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                    Tenure (Months) *
                  </label>
                  <Input
                    {...register('tenure_months')}
                    type="number"
                    min={1}
                    max={120}
                    placeholder="12"
                    error={errors.tenure_months?.message}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                    First Due Date *
                  </label>
                  <Input
                    {...register('first_due_date')}
                    type="date"
                    error={errors.first_due_date?.message}
                  />
                </div>
              </div>

              {/* Purpose */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-[var(--muted-ink)] mb-1">
                  Loan Purpose *
                </label>
                <Input
                  {...register('purpose')}
                  placeholder="e.g. Livestock purchase, agriculture seeds, dairy equipment"
                  error={errors.purpose?.message}
                />
              </div>

              {/* Form Action Buttons */}
              <div className="pt-4 border-t border-[var(--border)] flex flex-col gap-2">
                {hasBlockers && (
                  <div className="p-2.5 rounded bg-surface-sunken border border-danger/30 text-xs text-danger flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>Submission blocked: Resolve failing eligibility checks first.</span>
                  </div>
                )}

                <div className="flex items-center gap-3">
                  <Button
                    type="submit"
                    variant="primary"
                    disabled={isSubmitting || hasBlockers || !selectedMemberId}
                    onClick={() => setSubmitMode('submit')}
                    className="flex-1"
                  >
                    {isSubmitting && submitMode === 'submit'
                      ? 'Submitting...'
                      : 'Submit for Approval'}
                  </Button>
                  <Button
                    type="submit"
                    variant="secondary"
                    disabled={isSubmitting}
                    onClick={() => setSubmitMode('draft')}
                  >
                    Save as Draft
                  </Button>
                </div>
                <p className="text-[11px] text-[var(--muted-ink)] text-center">
                  Maker-checker policy applies: As applicant or creator, you cannot approve your
                  own loan.
                </p>
              </div>
            </div>

            {/* Eligibility Live Panel */}
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded p-5 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                <div className="flex items-center gap-2">
                  <CreditCard className="w-4 h-4 text-[var(--primary)]" />
                  <h3 className="font-serif text-base font-semibold text-[var(--ink)]">
                    Eligibility Engine (SPEC 6.2)
                  </h3>
                </div>
                {previewData?.eligibility && (
                  <span
                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${
                      previewData.eligibility.is_eligible
                        ? 'bg-primary-tint text-primary'
                        : 'bg-surface-sunken text-danger border border-danger/30'
                    }`}
                  >
                    {previewData.eligibility.is_eligible ? '[PASS] ELIGIBLE' : '[FAIL] INELIGIBLE'}
                  </span>
                )}
              </div>

              {!selectedMemberId ? (
                <div className="p-4 text-center text-xs text-[var(--muted-ink)] border border-dashed border-[var(--border)] rounded">
                  Select a member to evaluate savings multiple and repayment eligibility.
                </div>
              ) : isPreviewLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : previewData?.eligibility ? (
                <div className="space-y-3">
                  {previewData.eligibility.checks.map((check) => {
                    const isPass = check.passed;
                    const isBlocker = check.severity === 'BLOCKER';
                    const isWarn = check.severity === 'WARNING';

                    let badgeCue = '[INFO]';
                    let badgeClass = 'text-[var(--muted-ink)] border-border bg-surface-sunken';
                    if (isPass) {
                      badgeCue = '[PASS]';
                      badgeClass = 'text-primary border-primary/30 bg-primary-tint';
                    } else if (isBlocker) {
                      badgeCue = '[BLOCKER FAIL]';
                      badgeClass = 'text-danger border-danger/30 bg-surface-sunken font-bold';
                    } else if (isWarn) {
                      badgeCue = '[WARNING]';
                      badgeClass = 'text-warning border-warning/30 bg-surface-sunken font-semibold';
                    }

                    return (
                      <div
                        key={check.code}
                        className="p-3 rounded border border-[var(--border)] bg-[var(--surface-muted)] text-xs space-y-1"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-[var(--ink)]">{check.name}</span>
                          <span
                            className={`inline-block px-1.5 py-0.5 text-[10px] tracking-wide rounded border ${badgeClass}`}
                          >
                            {badgeCue}
                          </span>
                        </div>
                        <p className="text-[11px] text-[var(--muted-ink)] leading-relaxed">
                          {check.message}
                        </p>
                        {check.threshold_value && (
                          <div className="flex items-center gap-3 text-[10px] text-[var(--muted-ink)] font-mono pt-0.5">
                            <span>Actual: {check.actual_value}</span>
                            <span>|</span>
                            <span>Limit: {check.threshold_value}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-[var(--muted-ink)]">
                  Enter loan particulars to evaluate criteria.
                </p>
              )}
            </div>
          </div>

          {/* Right Column: Live Schedule Preview Table */}
          <div className="lg:col-span-7 space-y-4">
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded p-5 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-[var(--border)] pb-3">
                <div className="flex items-center gap-2">
                  <Calculator className="w-4 h-4 text-[var(--primary)]" />
                  <h3 className="font-serif text-base font-semibold text-[var(--ink)]">
                    Schedule Preview (SPEC 6.3)
                  </h3>
                </div>
                {isPreviewFetching && (
                  <span className="text-xs text-[var(--muted-ink)] animate-pulse">
                    Calculating schedule...
                  </span>
                )}
              </div>

              {previewData && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-[var(--surface-muted)] p-3 rounded border border-[var(--border)]">
                  <div>
                    <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Principal
                    </span>
                    <MoneyText
                      amount={previewData.principal}
                      className="text-sm font-semibold text-[var(--ink)]"
                    />
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Total Interest
                    </span>
                    <MoneyText
                      amount={previewData.total_interest}
                      className="text-sm font-semibold text-[var(--ink)]"
                    />
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Total Payable
                    </span>
                    <MoneyText
                      amount={previewData.total_amount}
                      className="text-sm font-semibold text-[var(--ink)]"
                    />
                  </div>
                  <div>
                    <span className="block text-[10px] uppercase font-semibold text-[var(--muted-ink)]">
                      Monthly EMI
                    </span>
                    <MoneyText
                      amount={previewData.monthly_installment}
                      className="text-sm font-bold text-[var(--primary)]"
                    />
                  </div>
                </div>
              )}

              {/* Installment Table */}
              <div className="overflow-x-auto border border-[var(--border)] rounded">
                <table className="w-full text-xs text-left border-collapse">
                  <thead>
                    <tr className="bg-[var(--surface-muted)] text-[var(--muted-ink)] border-b border-[var(--border)] font-semibold uppercase text-[10px] tracking-wider">
                      <th className="py-2 px-3">#</th>
                      <th className="py-2 px-3">Due Date</th>
                      <th className="py-2 px-3 text-right">Principal</th>
                      <th className="py-2 px-3 text-right">Interest</th>
                      <th className="py-2 px-3 text-right">Total Due</th>
                      <th className="py-2 px-3 text-right">Outstanding</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border)] font-mono">
                    {isPreviewLoading ? (
                      <tr>
                        <td colSpan={6} className="py-6 px-3 text-center">
                          <Skeleton className="h-6 w-full mb-2" />
                          <Skeleton className="h-6 w-full" />
                        </td>
                      </tr>
                    ) : previewData?.installments && previewData.installments.length > 0 ? (
                      previewData.installments.map((inst) => (
                        <tr
                          key={inst.installment_no}
                          className="hover:bg-[var(--surface-muted)] transition-colors"
                        >
                          <td className="py-2 px-3 text-[var(--ink)]">{inst.installment_no}</td>
                          <td className="py-2 px-3 text-[var(--ink)]">{inst.due_date}</td>
                          <td className="py-2 px-3 text-right text-[var(--ink)] tabular-nums">
                            <MoneyText amount={inst.principal_due} />
                          </td>
                          <td className="py-2 px-3 text-right text-[var(--ink)] tabular-nums">
                            <MoneyText amount={inst.interest_due} />
                          </td>
                          <td className="py-2 px-3 text-right font-medium text-[var(--ink)] tabular-nums">
                            <MoneyText amount={inst.total_due} />
                          </td>
                          <td className="py-2 px-3 text-right text-[var(--muted-ink)] tabular-nums">
                            <MoneyText amount={inst.outstanding_balance} />
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td
                          colSpan={6}
                          className="py-6 text-center text-xs text-[var(--muted-ink)] font-sans"
                        >
                          Fill loan inputs on the left to preview repayment amortization schedule.
                        </td>
                      </tr>
                    )}
                  </tbody>
                  {previewData?.installments && previewData.installments.length > 0 && (
                    <tfoot>
                      <tr className="bg-[var(--surface-muted)] font-bold border-t border-[var(--border)] text-xs">
                        <td colSpan={2} className="py-2.5 px-3 uppercase tracking-wider text-[var(--ink)] font-sans">
                          Total
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono tabular-nums text-[var(--ink)]">
                          <MoneyText amount={previewData.principal} />
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono tabular-nums text-[var(--ink)]">
                          <MoneyText amount={previewData.total_interest} />
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono tabular-nums text-[var(--primary)] font-bold">
                          <MoneyText amount={previewData.total_amount} />
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono tabular-nums text-[var(--muted-ink)]">
                          0.00
                        </td>
                      </tr>
                    </tfoot>
                  )}
                </table>
              </div>
              <p className="text-[11px] text-[var(--muted-ink)]">
                Note: In compliance with SPEC 6.3, final installment absorbs fractional residue so
                total principal strictly matches requested loan.
              </p>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
};
