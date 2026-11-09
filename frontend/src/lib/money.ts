import Decimal from "decimal.js";

export interface FormatMoneyOptions {
  includeSymbol?: boolean;
  decimals?: number;
}

/**
 * Parses any monetary string or number representation into Decimal.
 * Strictly avoids parseFloat to preserve decimal precision.
 */
export function parseMoney(amount: string | number | Decimal): Decimal {
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
