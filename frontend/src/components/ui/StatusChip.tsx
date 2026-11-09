import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export type StatusVariant =
  | "active"
  | "draft"
  | "submitted"
  | "approved"
  | "disbursed"
  | "overdue"
  | "closed"
  | "rejected"
  | "written_off"
  | "pending"
  | "paid"
  | "partial"
  | "neutral"
  | "success"
  | "warning"
  | "danger";

export interface StatusChipProps extends React.HTMLAttributes<HTMLSpanElement> {
  status?: string;
  variant?: StatusVariant;
  children?: React.ReactNode;
}

export function getStatusVariant(statusText: string): StatusVariant {
  const norm = statusText.toUpperCase().trim();
  switch (norm) {
    case "ACTIVE":
    case "PAID":
    case "APPROVED":
    case "HELD":
      return "active";
    case "OVERDUE":
    case "REJECTED":
    case "WRITTEN_OFF":
      return "overdue";
    case "SUBMITTED":
    case "PENDING":
    case "DISBURSED":
      return "submitted";
    case "PARTIAL":
      return "partial";
    case "CLOSED":
    case "DRAFT":
    case "CANCELLED":
    default:
      return "neutral";
  }
}

export const StatusChip: React.FC<StatusChipProps> = ({
  status,
  variant,
  children,
  className,
  ...props
}) => {
  const displayLabel = status || (typeof children === "string" ? children : "");
  let resolvedVariant = variant || getStatusVariant(displayLabel);
  if (resolvedVariant === "success") resolvedVariant = "active";
  if (resolvedVariant === "warning") resolvedVariant = "partial";
  if (resolvedVariant === "danger") resolvedVariant = "overdue";

  const variantStyles: Record<StatusVariant, string> = {
    active: "bg-primary-tint text-primary border-primary/20",
    success: "bg-primary-tint text-primary border-primary/20",
    submitted: "bg-surface-sunken text-info border-info/30",
    partial: "bg-surface-sunken text-warning border-warning/30",
    warning: "bg-surface-sunken text-warning border-warning/30",
    overdue: "bg-surface-sunken text-danger border-danger/30 font-semibold",
    danger: "bg-surface-sunken text-danger border-danger/30 font-semibold",
    draft: "bg-surface-sunken text-ink-muted border-border",
    approved: "bg-primary-tint text-primary border-primary/30",
    disbursed: "bg-primary-tint text-primary border-primary/30",
    closed: "bg-surface-sunken text-ink-muted border-border",
    rejected: "bg-surface-sunken text-danger border-danger/30",
    written_off: "bg-surface-sunken text-danger border-danger/30",
    pending: "bg-surface-sunken text-warning border-warning/30",
    paid: "bg-primary-tint text-primary border-primary/30",
    neutral: "bg-surface-sunken text-ink-muted border-border",
  };

  return (
    <span
      className={twMerge(
        clsx(
          "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border leading-none tracking-wide",
          variantStyles[resolvedVariant],
          className
        )
      )}
      {...props}
    >
      {children || status}
    </span>
  );
};
