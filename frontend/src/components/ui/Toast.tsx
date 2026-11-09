import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export type ToastType = "info" | "success" | "warning" | "danger";

export interface ToastProps extends React.HTMLAttributes<HTMLDivElement> {
  type?: ToastType;
  title: string;
  message?: string;
  onDismiss?: () => void;
}

export const Toast: React.FC<ToastProps> = ({
  type = "info",
  title,
  message,
  onDismiss,
  className,
  ...props
}) => {
  const typeStyles = {
    info: "border-info/40 bg-surface text-ink",
    success: "border-success/40 bg-surface text-ink",
    warning: "border-warning/40 bg-surface text-ink",
    danger: "border-danger/40 bg-surface text-ink",
  }[type];

  const badgeStyles = {
    info: "bg-info text-surface",
    success: "bg-success text-surface",
    warning: "bg-warning text-surface",
    danger: "bg-danger text-surface",
  }[type];

  return (
    <div
      role="status"
      aria-live="polite"
      className={twMerge(
        clsx(
          "flex items-start gap-3 w-full max-w-sm rounded-lg border p-4 shadow-overlay bg-surface transition-all",
          typeStyles,
          className
        )
      )}
      {...props}
    >
      <span className={clsx("h-2 w-2 rounded-full mt-1.5 shrink-0", badgeStyles)} aria-hidden="true" />
      <div className="flex-1 text-left">
        <h4 className="text-sm font-semibold text-ink leading-tight">{title}</h4>
        {message && <p className="mt-1 text-xs text-ink-muted leading-normal">{message}</p>}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="text-xs font-medium text-ink-muted hover:text-ink transition-colors p-1"
          aria-label="Dismiss toast"
        >
          ✕
        </button>
      )}
    </div>
  );
};
