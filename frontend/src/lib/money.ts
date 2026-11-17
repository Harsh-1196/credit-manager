import Decimal from "decimal.js";

export interface FormatMoneyOptions {
  includeSymbol?: boolean;
  decimals?: number;
}

/**
 * Parses any monetary string or number representation into Decimal.
 * Strictly avoids parseFloat to preserve decimal precision.
 */
export function parseMoney(amount: string | number | Decimal | null | undefined): Decimal {
  if (amount === null || amount === undefined) {
    return new Decimal(0);
  }
  if (amount instanceof Decimal) {
    return amount;
  }
  if (typeof amount === "number") {
    // Convert number to string first, never use float arithmetic
    return new Decimal(amount.toString());
  }
  const cleaned = amount.trim().replace(/,/g, "").replace(/₹/g, "");
  if (!cleaned) {
    return new Decimal(0);
  }
  return new Decimal(cleaned);
}

/**
 * Format a Decimal / monetary string into Indian number grouped currency (en-IN).
 * e.g. 100000 -> ₹1,00,000.00
 * e.g. 125000.5 -> ₹1,25,000.50
 */
export function formatIndianMoney(
  amount: string | number | Decimal,
  options: FormatMoneyOptions = {}
): string {
  const { includeSymbol = true, decimals = 2 } = options;
  const d = parseMoney(amount);
  const isNegative = d.isNegative();
  const abs = d.abs();

  // Quantize/fix to exact decimals without float math
  const fixedStr = abs.toFixed(decimals);
  const [intPart, decPart] = fixedStr.split(".");

  let groupedInt = "";
  if (intPart.length <= 3) {
    groupedInt = intPart;
  } else {
    const lastThree = intPart.slice(-3);
    const remaining = intPart.slice(0, -3);
    const withCommas = remaining.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    groupedInt = `${withCommas},${lastThree}`;
  }

  const formattedNumber = decPart !== undefined ? `${groupedInt}.${decPart}` : groupedInt;
  const symbol = includeSymbol ? "₹" : "";
  const sign = isNegative ? "-" : "";

  return `${sign}${symbol}${formattedNumber}`;
}

/**
 * Format an amount into an Indian abbreviated string (e.g., 1.2L, 85.4K, 2.5Cr),
 * specifically designed for headline key figures on the dashboard.
 * Returns both the abbreviated representation and the full formatted string for tooltips.
 */
export function formatIndianAbbreviated(
  amount: string | number | Decimal | null | undefined,
  options: { includeSymbol?: boolean } = {}
): { abbreviated: string; full: string } {
  const d = parseMoney(amount);
  const full = formatIndianMoney(d, { includeSymbol: options.includeSymbol ?? true, decimals: 2 });
  const symbol = (options.includeSymbol ?? true) ? "₹" : "";
  const abs = d.abs();
  const sign = d.isNegative() ? "-" : "";

  let numStr = "";
  if (abs.gte(10000000)) {
    const cr = abs.dividedBy(10000000);
    numStr = `${cr.toFixed(1).replace(/\.0$/, "")}Cr`;
  } else if (abs.gte(100000)) {
    const lk = abs.dividedBy(100000);
    numStr = `${lk.toFixed(1).replace(/\.0$/, "")}L`;
  } else if (abs.gte(1000)) {
    const th = abs.dividedBy(1000);
    numStr = `${th.toFixed(1).replace(/\.0$/, "")}K`;
  } else {
    numStr = abs.toFixed(2);
  }

  return {
    abbreviated: `${sign}${symbol}${numStr}`,
    full,
  };
}
