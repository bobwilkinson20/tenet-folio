import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ValuationWarning } from "../../components/dashboard/ValuationWarning";
import type { AccountSummary } from "../../types";

function makeAccount(
  overrides: Partial<AccountSummary> & { id: string; name: string },
): AccountSummary {
  return {
    provider_name: "SnapTrade",
    institution_name: null,
    value: "10000.00",
    last_sync_time: new Date().toISOString(),
    last_sync_status: "success",
    last_sync_error: null,
    balance_date: null,
    valuation_status: "ok",
    valuation_date: "2026-01-28",
    ...overrides,
  };
}

describe("ValuationWarning", () => {
  it("renders nothing when all accounts are ok", () => {
    const accounts = [
      makeAccount({ id: "1", name: "Acct A", valuation_status: "ok" }),
      makeAccount({ id: "2", name: "Acct B", valuation_status: "ok" }),
    ];
    const { container } = render(<ValuationWarning accounts={accounts} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when accounts is empty", () => {
    const { container } = render(<ValuationWarning accounts={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows banner listing missing accounts", () => {
    const accounts = [
      makeAccount({ id: "1", name: "Broken Account", valuation_status: "missing" }),
      makeAccount({ id: "2", name: "Good Account", valuation_status: "ok" }),
    ];
    render(<ValuationWarning accounts={accounts} />);

    expect(screen.getByTestId("valuation-warning")).toBeInTheDocument();
    expect(screen.getByText(/Broken Account/)).toBeInTheDocument();
    expect(screen.getByText(/missing valuation data/)).toBeInTheDocument();
    expect(screen.getByText(/re-syncing/)).toBeInTheDocument();
    // Should not list the good account
    expect(screen.queryByText(/Good Account/)).not.toBeInTheDocument();
  });

  it("shows banner listing partial and stale accounts", () => {
    const accounts = [
      makeAccount({ id: "1", name: "Partial Acct", valuation_status: "partial" }),
      makeAccount({ id: "2", name: "Stale Acct", valuation_status: "stale" }),
    ];
    render(<ValuationWarning accounts={accounts} />);

    expect(screen.getByTestId("valuation-warning")).toBeInTheDocument();
    expect(screen.getByText(/Partial Acct/)).toBeInTheDocument();
    expect(screen.getByText(/some holdings missing/)).toBeInTheDocument();
    expect(screen.getByText(/Stale Acct/)).toBeInTheDocument();
    expect(screen.getByText(/may be outdated/)).toBeInTheDocument();
  });

  it("ignores accounts with null valuation_status", () => {
    const accounts = [
      makeAccount({ id: "1", name: "Never Synced", valuation_status: null }),
      makeAccount({ id: "2", name: "Good", valuation_status: "ok" }),
    ];
    const { container } = render(<ValuationWarning accounts={accounts} />);
    expect(container.firstChild).toBeNull();
  });

  it("uses red styling when any account has missing status", () => {
    const accounts = [
      makeAccount({ id: "1", name: "Missing", valuation_status: "missing" }),
      makeAccount({ id: "2", name: "Partial", valuation_status: "partial" }),
    ];
    render(<ValuationWarning accounts={accounts} />);

    const banner = screen.getByTestId("valuation-warning");
    expect(banner.className).toContain("tf-negative");
  });

  it("uses yellow styling when no account has missing status", () => {
    const accounts = [
      makeAccount({ id: "1", name: "Stale", valuation_status: "stale" }),
    ];
    render(<ValuationWarning accounts={accounts} />);

    const banner = screen.getByTestId("valuation-warning");
    expect(banner.className).toContain("tf-warning");
    expect(banner.className).not.toContain("tf-negative");
  });
});
