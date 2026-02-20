import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { HoldingFormModal } from "../../components/accounts/HoldingFormModal";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    addHolding: vi.fn(),
    updateHolding: vi.fn(),
  },
}));

import { accountsApi } from "../../api/accounts";

const mockHolding = {
  id: "h-1",
  account_snapshot_id: "acct-snap-1",
  ticker: "HOME",
  quantity: 1,
  snapshot_price: 500000,
  snapshot_value: 500000,
  created_at: "2025-01-01T00:00:00Z",
  security_name: null,
};

const mockManualHolding = {
  id: "h-man-1",
  account_snapshot_id: "acct-snap-1",
  ticker: "_MAN:abc12345",
  quantity: 1,
  snapshot_price: 500000,
  snapshot_value: 500000,
  created_at: "2025-01-01T00:00:00Z",
  security_name: "Primary Residence",
};

describe("HoldingFormModal", () => {
  const mockOnClose = vi.fn();
  const mockOnSaved = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not render when isOpen is false", () => {
    render(
      <HoldingFormModal
        isOpen={false}
        holding={null}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );
    expect(screen.queryByText("Add Holding")).not.toBeInTheDocument();
  });

  it("renders create form when holding is null", () => {
    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );
    expect(screen.getByText("Add Holding")).toBeInTheDocument();
    expect(screen.getByTestId("holding-ticker")).toHaveValue("");
  });

  it("renders edit form pre-populated when holding provided", () => {
    render(
      <HoldingFormModal
        isOpen={true}
        holding={mockHolding}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );
    expect(screen.getByText("Edit Holding")).toBeInTheDocument();
    expect(screen.getByTestId("holding-ticker")).toHaveValue("HOME");
  });

  it("auto-calculates market_value from quantity and price", async () => {
    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.change(screen.getByTestId("holding-quantity"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByTestId("holding-price"), {
      target: { value: "150" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("holding-market-value")).toHaveValue(1500);
    });
  });

  it("calls addHolding API for new holding", async () => {
    vi.mocked(accountsApi.addHolding).mockResolvedValue({ data: { id: "h-new" } } as never);

    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.change(screen.getByTestId("holding-ticker"), {
      target: { value: "HOME" },
    });
    fireEvent.change(screen.getByTestId("holding-quantity"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByTestId("holding-market-value"), {
      target: { value: "500000" },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(accountsApi.addHolding).toHaveBeenCalledWith("acc-1", {
        ticker: "HOME",
        quantity: 1,
        market_value: 500000,
      });
      expect(mockOnSaved).toHaveBeenCalled();
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  it("calls updateHolding API for edit", async () => {
    vi.mocked(accountsApi.updateHolding).mockResolvedValue({ data: { id: "h-1" } } as never);

    render(
      <HoldingFormModal
        isOpen={true}
        holding={mockHolding}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.change(screen.getByTestId("holding-market-value"), {
      target: { value: "520000" },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(accountsApi.updateHolding).toHaveBeenCalledWith("acc-1", "h-1", expect.objectContaining({
        ticker: "HOME",
        market_value: 520000,
      }));
      expect(mockOnSaved).toHaveBeenCalled();
    });
  });

  it("shows error on failure", async () => {
    vi.mocked(accountsApi.addHolding).mockRejectedValue({
      response: { data: { detail: "Server error" } },
    });

    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.change(screen.getByTestId("holding-ticker"), {
      target: { value: "HOME" },
    });
    fireEvent.change(screen.getByTestId("holding-quantity"), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByTestId("holding-market-value"), {
      target: { value: "500000" },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(screen.getByTestId("holding-form-error")).toHaveTextContent("Server error");
    });
    expect(mockOnSaved).not.toHaveBeenCalled();
  });

  it("allows negative market value for liabilities", async () => {
    vi.mocked(accountsApi.addHolding).mockResolvedValue({ data: { id: "h-new" } } as never);

    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.click(screen.getByTestId("asset-type-other"));

    fireEvent.change(screen.getByTestId("holding-description"), {
      target: { value: "Mortgage" },
    });
    fireEvent.change(screen.getByTestId("holding-market-value"), {
      target: { value: "-350000" },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(accountsApi.addHolding).toHaveBeenCalledWith("acc-1", {
        description: "Mortgage",
        market_value: -350000,
      });
    });
  });

  it("shows duplicate warning when ticker already exists", () => {
    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        existingTickers={["VTI", "HOME"]}
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.change(screen.getByTestId("holding-ticker"), {
      target: { value: "vti" },
    });

    expect(screen.getByTestId("duplicate-ticker-warning")).toHaveTextContent(
      "A holding for VTI already exists",
    );
  });

  it("does not show duplicate warning for new ticker", () => {
    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        existingTickers={["VTI", "HOME"]}
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.change(screen.getByTestId("holding-ticker"), {
      target: { value: "AAPL" },
    });

    expect(screen.queryByTestId("duplicate-ticker-warning")).not.toBeInTheDocument();
  });

  it("validates ticker is required in security mode", async () => {
    render(
      <HoldingFormModal
        isOpen={true}
        holding={null}
        accountId="acc-1"
        onClose={mockOnClose}
        onSaved={mockOnSaved}
      />,
    );

    fireEvent.change(screen.getByTestId("holding-market-value"), {
      target: { value: "500000" },
    });
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(screen.getByText("Ticker is required")).toBeInTheDocument();
    });
    expect(accountsApi.addHolding).not.toHaveBeenCalled();
  });

  describe("asset type picker", () => {
    it("renders Security and Other buttons", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      expect(screen.getByTestId("asset-type-security")).toBeInTheDocument();
      expect(screen.getByTestId("asset-type-other")).toBeInTheDocument();
    });

    it("shows description and value fields in Other mode, hides ticker/qty/price", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      fireEvent.click(screen.getByTestId("asset-type-other"));

      expect(screen.getByTestId("holding-description")).toBeInTheDocument();
      expect(screen.getByTestId("holding-market-value")).toBeInTheDocument();
      expect(screen.queryByTestId("holding-ticker")).not.toBeInTheDocument();
      expect(screen.queryByTestId("holding-quantity")).not.toBeInTheDocument();
      expect(screen.queryByTestId("holding-price")).not.toBeInTheDocument();
    });

    it("submits description and market_value in Other mode", async () => {
      vi.mocked(accountsApi.addHolding).mockResolvedValue({ data: { id: "h-new" } } as never);

      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      fireEvent.click(screen.getByTestId("asset-type-other"));

      fireEvent.change(screen.getByTestId("holding-description"), {
        target: { value: "Primary Residence" },
      });
      fireEvent.change(screen.getByTestId("holding-market-value"), {
        target: { value: "500000" },
      });
      fireEvent.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(accountsApi.addHolding).toHaveBeenCalledWith("acc-1", {
          description: "Primary Residence",
          market_value: 500000,
        });
        expect(mockOnSaved).toHaveBeenCalled();
      });
    });

    it("validates description is required in Other mode", async () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      fireEvent.click(screen.getByTestId("asset-type-other"));

      fireEvent.change(screen.getByTestId("holding-market-value"), {
        target: { value: "500000" },
      });
      fireEvent.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(screen.getByText("Description is required")).toBeInTheDocument();
      });
      expect(accountsApi.addHolding).not.toHaveBeenCalled();
    });

    it("auto-selects Other mode and pre-populates description when editing _MAN: holding", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={mockManualHolding}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      expect(screen.getByTestId("asset-type-other")).toHaveClass("bg-tf-accent-primary");
      expect(screen.getByTestId("holding-description")).toHaveValue("Primary Residence");
      expect(screen.getByTestId("holding-market-value")).toHaveValue(500000);
    });

    it("disables asset type picker in edit mode with explanation", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={mockHolding}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      expect(screen.getByTestId("asset-type-security")).toBeDisabled();
      expect(screen.getByTestId("asset-type-other")).toBeDisabled();
      expect(screen.getByText(/cannot be changed/i)).toBeInTheDocument();
    });

    it("does not show disabled explanation in create mode", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      expect(screen.queryByText(/cannot be changed/i)).not.toBeInTheDocument();
    });
  });

  describe("cost basis fields", () => {
    it("shows cost basis fields in create mode", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      expect(screen.getByTestId("holding-acquisition-date")).toBeInTheDocument();
      expect(screen.getByTestId("holding-cost-basis")).toBeInTheDocument();
      expect(screen.getByText("Leave blank to default to current value")).toBeInTheDocument();
    });

    it("hides cost basis fields in edit mode", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={mockHolding}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      expect(screen.queryByTestId("holding-acquisition-date")).not.toBeInTheDocument();
      expect(screen.queryByTestId("holding-cost-basis")).not.toBeInTheDocument();
    });

    it("includes cost basis in API call when provided", async () => {
      vi.mocked(accountsApi.addHolding).mockResolvedValue({ data: { id: "h-new" } } as never);

      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      fireEvent.change(screen.getByTestId("holding-ticker"), {
        target: { value: "AAPL" },
      });
      fireEvent.change(screen.getByTestId("holding-quantity"), {
        target: { value: "10" },
      });
      fireEvent.change(screen.getByTestId("holding-market-value"), {
        target: { value: "1500" },
      });
      fireEvent.change(screen.getByTestId("holding-acquisition-date"), {
        target: { value: "2024-01-15" },
      });
      fireEvent.change(screen.getByTestId("holding-cost-basis"), {
        target: { value: "120" },
      });
      fireEvent.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(accountsApi.addHolding).toHaveBeenCalledWith("acc-1", {
          ticker: "AAPL",
          quantity: 10,
          market_value: 1500,
          acquisition_date: "2024-01-15",
          cost_basis_per_unit: 120,
        });
      });
    });

    it("shows 'Total Cost Basis' label in other mode", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      fireEvent.click(screen.getByTestId("asset-type-other"));

      expect(screen.getByText("Total Cost Basis")).toBeInTheDocument();
    });

    it("shows 'Cost Basis / Unit' label in security mode", () => {
      render(
        <HoldingFormModal
          isOpen={true}
          holding={null}
          accountId="acc-1"
          onClose={mockOnClose}
          onSaved={mockOnSaved}
        />,
      );

      expect(screen.getByText("Cost Basis / Unit")).toBeInTheDocument();
    });
  });
});
