import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { Button } from "./Button";

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  description,
  actionLabel,
  onAction,
  action,
  icon,
  className,
  ...props
}) => {
  return (
    <div
      className={twMerge(
        clsx(
          "flex flex-col items-center justify-center p-8 text-center rounded-lg border border-dashed border-border bg-surface/50",
          className
        )
      )}
      {...props}
    >
      {icon && (
        <div className="mb-3 text-ink-muted">
          {icon}
        </div>
      )}
      <h3 className="font-serif text-lg font-medium text-ink">{title}</h3>
      <p className="mt-1 text-sm text-ink-muted max-w-sm">{description}</p>
      {action ? (
        <div className="mt-4">{action}</div>
      ) : actionLabel && onAction ? (
        <div className="mt-4">
          <Button variant="primary" size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  );
};
