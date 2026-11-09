import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export interface StatProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  value: React.ReactNode;
  hint?: string;
  trend?: {
    value: string;
    isPositive?: boolean;
    textCue?: string;
  };
}

export const Stat: React.FC<StatProps> = ({
  label,
  value,
  hint,
  trend,
  className,
  ...props
}) => {
  return (
    <div
      className={twMerge(
        clsx(
          "flex flex-col border-b sm:border-b-0 sm:border-r last:border-b-0 last:border-r-0 border-border pb-4 sm:pb-0 sm:pr-6",
          className
        )
      )}
      {...props}
    >
      <span className="text-xs font-medium uppercase tracking-wider text-ink-muted">
        {label}
      </span>
      <div className="mt-1 font-serif text-3xl font-semibold tracking-tight text-ink tabular-nums">
        {value}
      </div>
      {trend && (
        <div className="mt-1 flex items-center gap-1.5 text-xs">
          <span
            className={clsx(
              "font-medium",
              trend.isPositive ? "text-success" : "text-danger"
            )}
          >
            {trend.value}
          </span>
          {trend.textCue && (
            <span className="text-ink-muted">({trend.textCue})</span>
          )}
        </div>
      )}
      {hint && !trend && (
        <span className="mt-1 text-xs text-ink-faint">{hint}</span>
      )}
    </div>
  );
};
