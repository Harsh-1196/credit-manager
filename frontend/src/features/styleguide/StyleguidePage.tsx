import React, { useState } from "react";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { StatusChip } from "../../components/ui/StatusChip";
import { Stat } from "../../components/ui/Stat";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/Table";
import { MoneyText } from "../../components/ui/MoneyText";
import { Dialog } from "../../components/ui/Dialog";
import { Toast } from "../../components/ui/Toast";
import { Skeleton } from "../../components/ui/Skeleton";
import { EmptyState } from "../../components/ui/EmptyState";
import { ThemeToggle } from "../../components/ui/ThemeToggle";
import { useTranslation } from "../../lib/i18n";

export const StyleguidePage: React.FC = () => {
  const { t } = useTranslation();
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [tableDense, setTableDense] = useState(false);

  const tokens = [
    { name: "--bg", label: "App Background", light: "#FAF8F4", dark: "#141816", cr: "14.86:1" },
    { name: "--surface", label: "Panels & Tables", light: "#FFFFFF", dark: "#1B201D", cr: "15.76:1" },
    { name: "--surface-sunken", label: "Wells & Inputs", light: "#F3EFE8", dark: "#222823", cr: "13.75:1" },
    { name: "--border", label: "Hairlines", light: "#E4DED3", dark: "#2E3530", cr: "Hairline" },
    { name: "--border-strong", label: "Dividers", light: "#CFC7B8", dark: "#434D46", cr: "Focus-adjacent" },
    { name: "--ink", label: "Primary Text", light: "#1F2421", dark: "#ECEAE4", cr: "14.86:1" },
    { name: "--ink-muted", label: "Secondary Text", light: "#5E655F", dark: "#A4ADA6", cr: "5.65:1" },
    { name: "--ink-faint", label: "Tertiary & Placeholders", light: "#727973", dark: "#78827A", cr: "4.50:1" },
    { name: "--primary", label: "Primary Actions & Links", light: "#2F5D50", dark: "#6FA593", cr: "7.06:1" },
    { name: "--accent", label: "Sparing Emphasis", light: "#9E4429", dark: "#D98062", cr: "5.98:1" },
    { name: "--success", label: "Positive & Repaid", light: "#376E46", dark: "#5FA872", cr: "5.69:1" },
    { name: "--warning", label: "Pending & Grace Period", light: "#855909", dark: "#D9A34A", cr: "5.77:1" },
    { name: "--danger", label: "Overdue & Errors", light: "#A63D2F", dark: "#E06B5A", cr: "5.95:1" },
    { name: "--info", label: "System Notes", light: "#35607F", dark: "#65A3D0", cr: "6.32:1" },
  ];

  return (
    <div className="min-h-screen bg-bg text-ink py-10 px-4 sm:px-8 max-w-7xl mx-auto space-y-16">
      {/* Header bar */}
      <header className="border-b border-border pb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-primary">
            {t("styleguide.badge")}
          </span>
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink mt-1">
            {t("styleguide.title")}
          </h1>
          <p className="text-sm text-ink-muted mt-1">
            {t("styleguide.description")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle />
        </div>
      </header>

      {/* 1. Semantic Color Tokens */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.colorTokens")}
          </h2>
          <p className="text-xs text-ink-muted">
            All colors map to semantic CSS variables with verified WCAG 2.2 AA contrast compliance.
          </p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7 gap-3">
          {tokens.map((token) => (
            <div
              key={token.name}
              className="p-3 rounded-lg border border-border bg-surface flex flex-col justify-between h-36"
            >
              <div
                className="w-full h-12 rounded-sm border border-border"
                style={{ backgroundColor: `var(${token.name})` }}
              />
              <div className="mt-2 text-left">
                <code className="text-[11px] font-mono font-semibold text-ink block truncate">
                  {token.name}
                </code>
                <span className="text-[10px] text-ink-muted block truncate">{token.label}</span>
                <span className="text-[9px] text-ink-faint block">CR: {token.cr}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Key Stats & Figures */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.stats")}
          </h2>
          <p className="text-xs text-ink-muted">
            Editorial figures set in Fraunces serif face. Borders over shadows, avoiding uniform card grids.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 p-6 rounded-lg border border-border bg-surface">
          <Stat
            label="Total Group Corpus"
            value={<MoneyText amount="485200.00" hideTextCue />}
            hint="Pooled member savings & surplus"
          />
          <Stat
            label="Outstanding Loans"
            value={<MoneyText amount="175000.00" hideTextCue />}
            trend={{ value: "+12.4%", isPositive: true, textCue: "active cycle" }}
          />
          <Stat
            label="Collections Due"
            value={<MoneyText amount="32400.00" hideTextCue />}
            hint="Next meeting: 15 Nov"
          />
          <Stat
            label="Portfolio at Risk (PAR)"
            value={<MoneyText amount="8500.00" isOverdue overdueDays={14} />}
            trend={{ value: "2.1%", isPositive: false, textCue: "overdue > 30d" }}
          />
        </div>
      </section>

      {/* 3. MoneyText & Indian Grouping */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.moneyFormatting")}
          </h2>
          <p className="text-xs text-ink-muted">
            Strict en-IN lakh/crore grouping, tabular numerals, 2 decimal places, and mandatory accessible non-color text cues.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg border border-border bg-surface text-left space-y-1">
            <span className="text-xs text-ink-muted block">Zero Amount:</span>
            <div className="text-lg">
              <MoneyText amount="0" />
            </div>
          </div>
          <div className="p-4 rounded-lg border border-border bg-surface text-left space-y-1">
            <span className="text-xs text-ink-muted block">One Lakh Grouping (₹1,00,000.00):</span>
            <div className="text-lg">
              <MoneyText amount="100000.00" />
            </div>
          </div>
          <div className="p-4 rounded-lg border border-border bg-surface text-left space-y-1">
            <span className="text-xs text-ink-muted block">Ten Lakhs (₹10,00,000.00):</span>
            <div className="text-lg">
              <MoneyText amount="1000000.00" />
            </div>
          </div>
          <div className="p-4 rounded-lg border border-border bg-surface text-left space-y-1">
            <span className="text-xs text-ink-muted block">Negative Balance (with Text Cue):</span>
            <div className="text-lg">
              <MoneyText amount="-1450.50" />
            </div>
          </div>
          <div className="p-4 rounded-lg border border-border bg-surface text-left space-y-1">
            <span className="text-xs text-ink-muted block">Overdue Installment (Color + Cue):</span>
            <div className="text-lg">
              <MoneyText amount="3500.00" isOverdue overdueDays={21} />
            </div>
          </div>
          <div className="p-4 rounded-lg border border-border bg-surface text-left space-y-1">
            <span className="text-xs text-ink-muted block">Right-Aligned Ledger Display:</span>
            <div className="text-lg text-right">
              <MoneyText amount="74520.00" align="right" />
            </div>
          </div>
        </div>
      </section>

      {/* 4. Ruled Ledger Table */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2 flex items-center justify-between">
          <div>
            <h2 className="font-serif text-2xl font-semibold text-ink">
              {t("styleguide.tables")}
            </h2>
            <p className="text-xs text-ink-muted">
              Ruled-ledger styling with separated debit/credit columns and right-aligned tabular numerals.
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setTableDense(!tableDense)}
          >
            {tableDense ? "Comfortable View" : "Dense View"}
          </Button>
        </div>
        <Table dense={tableDense}>
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead>
              <TableHead>Particulars</TableHead>
              <TableHead>Member / Reference</TableHead>
              <TableHead align="right">Debit (₹)</TableHead>
              <TableHead align="right">Credit (₹)</TableHead>
              <TableHead align="right">Balance (₹)</TableHead>
              <TableHead align="center">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell>2026-11-01</TableCell>
              <TableCell className="font-medium">Monthly Compulsory Savings</TableCell>
              <TableCell>SHG-MEM-001 (Sunita Devi)</TableCell>
              <TableCell align="right">—</TableCell>
              <TableCell align="right"><MoneyText amount="500.00" hideTextCue /></TableCell>
              <TableCell align="right"><MoneyText amount="12500.00" hideTextCue /></TableCell>
              <TableCell align="center"><StatusChip status="PAID" /></TableCell>
            </TableRow>
            <TableRow>
              <TableCell>2026-11-01</TableCell>
              <TableCell className="font-medium">Loan Repayment #4 (Principal + Interest)</TableCell>
              <TableCell>LN-2026-004 (Meena Kumari)</TableCell>
              <TableCell align="right">—</TableCell>
              <TableCell align="right"><MoneyText amount="2450.00" hideTextCue /></TableCell>
              <TableCell align="right"><MoneyText amount="14950.00" hideTextCue /></TableCell>
              <TableCell align="center"><StatusChip status="ACTIVE" /></TableCell>
            </TableRow>
            <TableRow>
              <TableCell>2026-11-02</TableCell>
              <TableCell className="font-medium">Emergency Loan Disbursal</TableCell>
              <TableCell>LN-2026-009 (Asha Devi)</TableCell>
              <TableCell align="right"><MoneyText amount="15000.00" hideTextCue /></TableCell>
              <TableCell align="right">—</TableCell>
              <TableCell align="right"><MoneyText amount="-50.00" /></TableCell>
              <TableCell align="center"><StatusChip status="DISBURSED" /></TableCell>
            </TableRow>
            <TableRow>
              <TableCell>2026-11-05</TableCell>
              <TableCell className="font-medium">Meeting Late Fine</TableCell>
              <TableCell>SHG-MEM-011 (Radha Bai)</TableCell>
              <TableCell align="right">—</TableCell>
              <TableCell align="right"><MoneyText amount="50.00" isOverdue overdueDays={5} /></TableCell>
              <TableCell align="right"><MoneyText amount="0.00" hideTextCue /></TableCell>
              <TableCell align="center"><StatusChip status="OVERDUE" /></TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </section>

      {/* 5. Buttons */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.buttons")}
          </h2>
          <p className="text-xs text-ink-muted">
            Four semantic variants. Flat borders over shadows, 6px button radius.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <Button variant="primary" size="md">Primary Action</Button>
          <Button variant="secondary" size="md">Secondary Action</Button>
          <Button variant="ghost" size="md">Ghost Action</Button>
          <Button variant="danger" size="md">Danger / Reversal</Button>
          <Button variant="primary" size="md" isLoading>Saving Entry</Button>
          <Button variant="secondary" size="md" disabled>Disabled Action</Button>
        </div>
        <div className="flex flex-wrap items-center gap-4 pt-2">
          <Button variant="secondary" size="sm">Small (32px)</Button>
          <Button variant="secondary" size="md">Medium (36px)</Button>
          <Button variant="secondary" size="lg">Large (44px)</Button>
        </div>
      </section>

      {/* 6. Form Controls */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.inputs")}
          </h2>
          <p className="text-xs text-ink-muted">
            Calm sunken surfaces, clear focus borders, and inline validation message anchors.
          </p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <Input
            label="Member Full Name"
            placeholder="e.g. Kaushalya Devi"
            helperText="Matches government ID proof"
          />
          <Input
            label="Requested Loan Amount (₹)"
            defaultValue="25000"
            error="Amount exceeds 4x savings multiple limit (max ₹20,000)"
          />
          <Select
            label="Loan Purpose"
            options={[
              { value: "agriculture", label: "Agricultural Inputs / Seeds" },
              { value: "livestock", label: "Dairy & Livestock" },
              { value: "business", label: "Small Trade / Kirana" },
              { value: "education", label: "Children Education" },
            ]}
            helperText="Categorized for reporting"
          />
        </div>
      </section>

      {/* 7. Status Chips */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.statusChips")}
          </h2>
          <p className="text-xs text-ink-muted">
            State machine indicators. Pill shapes permitted only for status chips per SPEC.
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          <StatusChip status="DRAFT" />
          <StatusChip status="SUBMITTED" />
          <StatusChip status="APPROVED" />
          <StatusChip status="DISBURSED" />
          <StatusChip status="ACTIVE" />
          <StatusChip status="PARTIAL" />
          <StatusChip status="PENDING" />
          <StatusChip status="PAID" />
          <StatusChip status="OVERDUE" />
          <StatusChip status="CLOSED" />
          <StatusChip status="REJECTED" />
          <StatusChip status="WRITTEN_OFF" />
        </div>
      </section>

      {/* 8. Feedback, Dialogs & Toasts */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.feedback")}
          </h2>
          <p className="text-xs text-ink-muted">
            Accessible notifications, confirmation modals with restated monetary amounts, and empty states.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-ink">Toast Notifications</h3>
            <Toast
              type="success"
              title="Journal Entry Posted"
              message="Collection sheet for Meeting #14 committed atomically."
            />
            <Toast
              type="danger"
              title="Maker-Checker Conflict"
              message="Group leader cannot approve their own loan application."
            />
          </div>
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-ink">Modal Dialog Confirmation</h3>
            <div className="p-4 rounded-lg border border-border bg-surface text-left">
              <p className="text-xs text-ink-muted mb-3">
                Financial actions require explicit restatement of amounts and members:
              </p>
              <Button variant="primary" size="sm" onClick={() => setIsDialogOpen(true)}>
                Open Disbursal Confirmation
              </Button>
            </div>
            <Dialog
              isOpen={isDialogOpen}
              onClose={() => setIsDialogOpen(false)}
              title="Confirm Loan Disbursal"
              description="Please review the journal allocation before releasing funds."
              confirmLabel="Disburse ₹25,000.00"
              onConfirm={() => setIsDialogOpen(false)}
            >
              <div className="space-y-2 py-2">
                <div className="flex justify-between border-b border-border pb-1">
                  <span className="text-ink-muted">Borrower:</span>
                  <span className="font-medium text-ink">Sunita Devi (SHG-MEM-001)</span>
                </div>
                <div className="flex justify-between border-b border-border pb-1">
                  <span className="text-ink-muted">Disbursal Amount:</span>
                  <span className="font-semibold text-ink">₹25,000.00</span>
                </div>
                <div className="flex justify-between text-xs text-ink-faint">
                  <span>Ledger Debit:</span>
                  <span>Loans Receivable (1100, Sunita Devi)</span>
                </div>
                <div className="flex justify-between text-xs text-ink-faint">
                  <span>Ledger Credit:</span>
                  <span>Cash in Hand (1000)</span>
                </div>
              </div>
            </Dialog>
          </div>
        </div>

        <div className="mt-6">
          <EmptyState
            title="No Loan Applications Pending Approval"
            description="All submitted member loans have been reviewed or disbursed for this group."
            actionLabel="Apply For Loan"
            onAction={() => alert("Navigate to loan application")}
          />
        </div>
      </section>

      {/* 9. Skeletons */}
      <section className="space-y-6">
        <div className="border-b border-border pb-2">
          <h2 className="font-serif text-2xl font-semibold text-ink">
            {t("styleguide.loadingStates")}
          </h2>
          <p className="text-xs text-ink-muted">
            Calm, non-glowing skeletons for loading views.
          </p>
        </div>
        <div className="p-6 rounded-lg border border-border bg-surface space-y-4">
          <Skeleton variant="text" width="40%" height={20} />
          <Skeleton variant="rectangular" height={40} />
          <div className="grid grid-cols-3 gap-4">
            <Skeleton variant="rectangular" height={80} />
            <Skeleton variant="rectangular" height={80} />
            <Skeleton variant="rectangular" height={80} />
          </div>
        </div>
      </section>
    </div>
  );
};
