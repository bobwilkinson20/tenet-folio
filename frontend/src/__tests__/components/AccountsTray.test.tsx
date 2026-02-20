import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { AccountsTray } from "../../components/dashboard/AccountsTray";
import type { AccountSummary } from "../../types";

const noop = () => {};

function renderTray(
  accounts: AccountSummary[],
  isOpen: boolean,
  selectedAccountIds: string[] | null = null,
  onSelectionChange: (ids: string[] | null) => void = noop,
) {
  return render(
    <MemoryRouter>
      <AccountsTray
        accounts={accounts}
        isOpen={isOpen}
        selectedAccountIds={selectedAccountIds}
        onSelectionChange={onSelectionChange}
      />
    </MemoryRouter>,
  );
}

const baseAccounts: AccountSummary[] = [
  {
    id: "acc-1",
    name: "Brokerage Account",
    provider_name: "SnapTrade",
    institution_name: "Vanguard",
    value: "50000.00",
    last_sync_time: new Date().toISOString(),
    last_sync_status: "success",
    last_sync_error: null,
    balance_date: "2026-01-28T12:00:00Z",
    valuation_status: "ok",
    valuation_date: "2026-01-28",
  },
  {
    id: "acc-2",
    name: "Retirement Fund",
    provider_name: "SnapTrade",
    institution_name: "Vanguard",
    value: "75000.00",
    last_sync_time: null,
    last_sync_status: null,
    last_sync_error: null,
    balance_date: null,
    valuation_status: "ok",
    valuation_date: "2026-01-28",
  },
  {
    id: "acc-3",
    name: "Savings",
    provider_name: "SimpleFIN",
    institution_name: "Fidelity",
    value: "25000.00",
    last_sync_time: new Date().toISOString(),
    last_sync_status: "success",
    last_sync_error: null,
    balance_date: "2026-01-28T12:00:00Z",
    valuation_status: "ok",
    valuation_date: "2026-01-28",
  },
  {
    id: "acc-4",
    name: "Checking",
    provider_name: "SimpleFIN",
    institution_name: null,
    value: "5000.00",
    last_sync_time: new Date().toISOString(),
    last_sync_status: "error",
    last_sync_error: "Connection failed",
    balance_date: null,
    valuation_status: "ok",
    valuation_date: "2026-01-28",
  },
];

describe("AccountsTray", () => {
  it("renders account names, institutions, and values", () => {
    renderTray(baseAccounts, true);

    expect(screen.getByText("Brokerage Account")).toBeInTheDocument();
    expect(screen.getByText("Retirement Fund")).toBeInTheDocument();
    expect(screen.getByText("Savings")).toBeInTheDocument();
    expect(screen.getByText("Checking")).toBeInTheDocument();

    expect(screen.getByText("$50,000.00")).toBeInTheDocument();
    expect(screen.getByText("$75,000.00")).toBeInTheDocument();
    expect(screen.getByText("$25,000.00")).toBeInTheDocument();
    expect(screen.getByText("$5,000.00")).toBeInTheDocument();
  });

  it("groups accounts by institution", () => {
    renderTray(baseAccounts, true);

    // Vanguard and Fidelity groups; acc-4 has no institution_name so falls back to SimpleFIN
    const groupHeaders = screen.getAllByText(
      /^(Vanguard|Fidelity|SimpleFIN)$/,
    );
    // Vanguard header + 2 sub-labels, Fidelity header + 1 sub-label, SimpleFIN header + 1 sub-label
    expect(groupHeaders.length).toBeGreaterThanOrEqual(3);
  });

  it("sorts groups alphabetically", () => {
    renderTray(baseAccounts, true);

    const tray = screen.getByTestId("accounts-tray");
    const text = tray.textContent ?? "";
    const fidelityIdx = text.indexOf("Fidelity");
    const simplefinIdx = text.indexOf("SimpleFIN");
    const vanguardIdx = text.indexOf("Vanguard");

    expect(fidelityIdx).toBeLessThan(simplefinIdx);
    expect(simplefinIdx).toBeLessThan(vanguardIdx);
  });

  it("sorts accounts within a group alphabetically", () => {
    renderTray(baseAccounts, true);

    const tray = screen.getByTestId("accounts-tray");
    const text = tray.textContent ?? "";
    const brokerageIdx = text.indexOf("Brokerage Account");
    const retirementIdx = text.indexOf("Retirement Fund");

    // Both in Vanguard group — Brokerage before Retirement
    expect(brokerageIdx).toBeLessThan(retirementIdx);
  });

  it("shows sync status icons with correct state", () => {
    renderTray(baseAccounts, true);

    // acc-1 recent success → green
    expect(screen.getByTestId("tray-sync-ok-acc-1")).toBeInTheDocument();
    // acc-2 no sync time → yellow
    expect(screen.getByTestId("tray-sync-warning-acc-2")).toBeInTheDocument();
    // acc-3 recent success → green
    expect(screen.getByTestId("tray-sync-ok-acc-3")).toBeInTheDocument();
    // acc-4 error → red
    expect(screen.getByTestId("tray-sync-error-acc-4")).toBeInTheDocument();
  });

  it("has zero width when isOpen is false", () => {
    renderTray(baseAccounts, false);

    const tray = screen.getByTestId("accounts-tray");
    expect(tray.className).toContain("w-0");
  });

  it("has full width when isOpen is true", () => {
    renderTray(baseAccounts, true);

    const tray = screen.getByTestId("accounts-tray");
    expect(tray.className).toContain("w-72");
    expect(tray.className).not.toContain("w-0");
  });

  it("contains links to account detail pages", () => {
    renderTray(baseAccounts, true);

    const row1 = screen.getByTestId("tray-account-acc-1");
    const link1 = row1.querySelector('a[href="/accounts/acc-1"]');
    expect(link1).toBeInTheDocument();

    const row3 = screen.getByTestId("tray-account-acc-3");
    const link3 = row3.querySelector('a[href="/accounts/acc-3"]');
    expect(link3).toBeInTheDocument();
  });

  it("shows empty state when no accounts", () => {
    renderTray([], true);

    expect(screen.getByText("No accounts found.")).toBeInTheDocument();
  });

  it("shows manual account icon", () => {
    const manualAccount: AccountSummary[] = [
      {
        id: "acc-manual",
        name: "My House",
        provider_name: "Manual",
        institution_name: null,
        value: "500000.00",
        last_sync_time: null,
        last_sync_status: null,
        last_sync_error: null,
        balance_date: "2026-01-15T00:00:00Z",
        valuation_status: "ok",
        valuation_date: "2026-01-15",
      },
    ];

    renderTray(manualAccount, true);

    const icon = screen.getByTestId("tray-sync-manual-acc-manual");
    expect(icon).toBeInTheDocument();
    const titleEl = icon.querySelector("title");
    expect(titleEl?.textContent).toContain("Manual account");
  });

  describe("account selection", () => {
    it("shows All and None buttons in header", () => {
      renderTray(baseAccounts, true);

      expect(screen.getByTestId("tray-select-all")).toBeInTheDocument();
      expect(screen.getByTestId("tray-select-none")).toBeInTheDocument();
    });

    it("all checkboxes are checked when selectedAccountIds is null", () => {
      renderTray(baseAccounts, true, null);

      for (const acc of baseAccounts) {
        const checkbox = screen.getByTestId(`tray-checkbox-${acc.id}`) as HTMLInputElement;
        expect(checkbox.checked).toBe(true);
      }
    });

    it("only selected checkboxes are checked", () => {
      renderTray(baseAccounts, true, ["acc-1", "acc-3"]);

      expect((screen.getByTestId("tray-checkbox-acc-1") as HTMLInputElement).checked).toBe(true);
      expect((screen.getByTestId("tray-checkbox-acc-2") as HTMLInputElement).checked).toBe(false);
      expect((screen.getByTestId("tray-checkbox-acc-3") as HTMLInputElement).checked).toBe(true);
      expect((screen.getByTestId("tray-checkbox-acc-4") as HTMLInputElement).checked).toBe(false);
    });

    it("unchecking from null transitions to explicit list", () => {
      const onChange = vi.fn();
      renderTray(baseAccounts, true, null, onChange);

      fireEvent.click(screen.getByTestId("tray-checkbox-acc-2"));

      // Should be called with all IDs except acc-2
      expect(onChange).toHaveBeenCalledTimes(1);
      const result = onChange.mock.calls[0][0] as string[];
      expect(result).not.toContain("acc-2");
      expect(result).toContain("acc-1");
      expect(result).toContain("acc-3");
      expect(result).toContain("acc-4");
    });

    it("checking last unchecked transitions back to null", () => {
      const onChange = vi.fn();
      // All selected except acc-2
      renderTray(baseAccounts, true, ["acc-1", "acc-3", "acc-4"], onChange);

      fireEvent.click(screen.getByTestId("tray-checkbox-acc-2"));

      // All accounts now selected → should return null
      expect(onChange).toHaveBeenCalledWith(null);
    });

    it("clicking All calls onSelectionChange with null", () => {
      const onChange = vi.fn();
      renderTray(baseAccounts, true, ["acc-1"], onChange);

      fireEvent.click(screen.getByTestId("tray-select-all"));

      expect(onChange).toHaveBeenCalledWith(null);
    });

    it("clicking None calls onSelectionChange with empty array", () => {
      const onChange = vi.fn();
      renderTray(baseAccounts, true, null, onChange);

      fireEvent.click(screen.getByTestId("tray-select-none"));

      expect(onChange).toHaveBeenCalledWith([]);
    });
  });
});
