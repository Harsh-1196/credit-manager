import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MoneyText } from "../src/components/ui/MoneyText";
import { formatIndianMoney } from "../src/lib/money";
import Decimal from "decimal.js";

describe("Money formatting utility (formatIndianMoney)", () => {
  it("formats zero with exactly two decimals", () => {
    expect(formatIndianMoney("0")).toBe("₹0.00");
    expect(formatIndianMoney("0.00")).toBe("₹0.00");
    expect(formatIndianMoney(0)).toBe("₹0.00");
  });

  it("formats standard thousands correctly", () => {
    expect(formatIndianMoney("1000")).toBe("₹1,000.00");
    expect(formatIndianMoney("5432.10")).toBe("₹5,432.10");
  });

  it("formats Indian lakh grouping correctly", () => {
    expect(formatIndianMoney("100000")).toBe("₹1,00,000.00");
    expect(formatIndianMoney("125000.00")).toBe("₹1,25,000.00");
    expect(formatIndianMoney("125000.50")).toBe("₹1,25,000.50");
    expect(formatIndianMoney("1000000")).toBe("₹10,00,000.00");
  });

  it("formats Indian crore grouping correctly", () => {
    expect(formatIndianMoney("10000000")).toBe("₹1,00,00,000.00");
    expect(formatIndianMoney("12345678.90")).toBe("₹1,23,45,678.90");
  });

  it("formats negative amounts with leading minus without float math", () => {
    expect(formatIndianMoney("-1500.00")).toBe("-₹1,500.00");
    expect(formatIndianMoney("-45000.25")).toBe("-₹45,000.25");
  });

  it("accepts Decimal instances directly", () => {
    const d = new Decimal("75000.75");
    expect(formatIndianMoney(d)).toBe("₹75,000.75");
  });
});

describe("MoneyText Component", () => {
  it("renders standard formatted amount with tabular-nums", () => {
    render(<MoneyText amount="100000.00" />);
    const valueEl = screen.getByTestId("money-value");
    expect(valueEl).toHaveTextContent("₹1,00,00,000.00".slice(0, 0) + "₹1,00,000.00");
    expect(screen.getByRole("generic", { name: "₹1,00,000.00" })).toBeInTheDocument();
  });

  it("renders zero amount properly", () => {
    render(<MoneyText amount="0" />);
    expect(screen.getByTestId("money-value")).toHaveTextContent("₹0.00");
  });

  it("renders negative values with leading minus and visible text cue", () => {
    render(<MoneyText amount="-2500.00" />);
    expect(screen.getByTestId("money-value")).toHaveTextContent("-₹2,500.00");
    const cue = screen.getByTestId("negative-cue");
    expect(cue).toBeInTheDocument();
    expect(cue).toHaveTextContent("Negative");
    // Verify color isn't the only signal
    expect(screen.getByRole("generic", { name: "Negative -₹2,500.00" })).toBeInTheDocument();
  });

  it("renders overdue values with color plus visible text cue", () => {
    render(<MoneyText amount="4500.00" isOverdue overdueDays={14} />);
    expect(screen.getByTestId("money-value")).toHaveTextContent("₹4,500.00");
    const overdueCue = screen.getByTestId("overdue-cue");
    expect(overdueCue).toBeInTheDocument();
    expect(overdueCue).toHaveTextContent("Overdue 14d");
    expect(screen.getByRole("generic", { name: "₹4,500.00 Overdue 14 days" })).toBeInTheDocument();
  });

  it("supports right alignment for tables and ledgers", () => {
    const { container } = render(<MoneyText amount="12500.00" align="right" />);
    expect(container.firstChild).toHaveClass("text-right");
  });
});
