import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import Decimal from "decimal.js";
import { formatIndianMoney, parseMoney } from "../../lib/money";

export interface MoneyTextProps extends React.HTMLAttributes<HTMLSpanElement> {
  amount: string | number | Decimal;
  isOverdue?: boolean;
  overdueDays?: number;
  overdueLabel?: string;
  align?: "right" | "left" | "center" | "inherit";
  showSymbol?: boolean;
  decimals?: number;
  hideTextCue?: boolean;
}

export const MoneyText: React.FC<MoneyTextProps> = ({
  amount,
  isOverdue = false,
  overdueDays,
  overdueLabel,
  align = "inherit",
  showSymbol = true,
  decimals = 2,
  hideTextCue = false,
  className,
  ...props
}) => {
  const parsed = parseMoney(amount);
  const isNegative = parsed.isNegative() && !parsed.isZero();
  const formatted = formatIndianMoney(parsed, { includeSymbol: showSymbol, decimals });

  const alignClass = {
    right: "text-right justify-end",
    left: "text-left justify-start",
    center: "text-center justify-center",
    inherit: "",
  }[align];

  // Accessible descriptive label
  const ariaLabelParts: string[] = [];
  if (isNegative) ariaLabelParts.push("Negative");
  ariaLabelParts.push(formatted);
  if (isOverdue) {
    ariaLabelParts.push(overdueDays ? `Overdue ${overdueDays} days` : "Overdue");
  }

  return (
    <span
      className={twMerge(
        clsx(
          "inline-flex items-baseline gap-1.5 tabular-nums font-mono-nums",
          alignClass,
          isOverdue && "text-danger font-medium",
          isNegative && !isOverdue && "text-danger font-medium",
          !isOverdue && !isNegative && "text-ink",
          className
        )
      )}
      aria-label={ariaLabelParts.join(" ")}
      {...props}
    >
      <span data-testid="money-value">{formatted}</span>

      {/* Accessible non-color cues */}
      {!hideTextCue && isOverdue && (
        <span
          data-testid="overdue-cue"
          className="text-[11px] font-sans font-medium uppercase tracking-wider text-danger bg-danger/10 px-1 py-0.2 rounded"
          aria-hidden="true"
        >
          {overdueLabel || (overdueDays ? `Overdue ${overdueDays}d` : "Overdue")}
        </span>
      )}

      {!hideTextCue && isNegative && !isOverdue && (
        <span
          data-testid="negative-cue"
          className="text-[11px] font-sans font-medium uppercase tracking-wider text-danger bg-danger/10 px-1 py-0.2 rounded"
          aria-hidden="true"
        >
          Negative
        </span>
      )}
    </span>
  );
};
