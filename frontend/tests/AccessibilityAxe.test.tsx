import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LoginPage } from "../src/features/auth/LoginPage";
import { MoneyText } from "../src/components/ui/MoneyText";
import { CommandPalette } from "../src/components/layout/CommandPalette";
import { AuthProvider } from "../src/lib/auth/AuthContext";

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
}

describe("Accessibility & Axe Automated Audit (Phase 7 / SPEC 12.7 & 17)", () => {
  it("LoginPage passes automated axe accessibility scan with 0 violations", async () => {
    const qc = createTestQueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <BrowserRouter>
            <LoginPage />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    );

    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it("MoneyText tabular numerals maintain accessible label and screen-reader semantics", async () => {
    const { container } = render(
      <div>
        <label htmlFor="amt">Due Amount</label>
        <MoneyText id="amt" amount="18450.00" />
      </div>
    );

    const results = await axe(container);
    expect(results.violations).toEqual([]);
    expect(screen.getByText("₹18,450.00")).toBeInTheDocument();
  });

  it("CommandPalette opens with Ctrl+K and passes axe accessibility scan", async () => {
    const qc = createTestQueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <BrowserRouter>
            <CommandPalette />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    );

    // Press Ctrl+K to open
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));

    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });

  it("Keyboard-only walkthrough: Tab navigation through form elements", async () => {
    const user = userEvent.setup();
    const qc = createTestQueryClient();
    render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <BrowserRouter>
            <LoginPage />
          </BrowserRouter>
        </AuthProvider>
      </QueryClientProvider>
    );

    // Initial Tab lands on theme toggle button
    await user.tab();
    const themeBtn = screen.getByRole("button", { name: /switch to dark theme/i });
    expect(themeBtn).toHaveFocus();

    // Next Tab lands on email input
    await user.tab();
    const emailInput = screen.getByLabelText(/email address/i);
    expect(emailInput).toHaveFocus();

    // Next Tab lands on password input
    await user.tab();
    const passwordInput = screen.getByLabelText(/password/i);
    expect(passwordInput).toHaveFocus();

    // Next Tab lands on sign in button
    await user.tab();
    const submitBtn = screen.getByRole("button", { name: /sign in/i });
    expect(submitBtn).toHaveFocus();
  });
});
