import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { LotFormModal } from "../../components/lots/LotFormModal";
import type { HoldingLot } from "../../types";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    createLot: vi.fn(),
    updateLot: vi.fn(),
    saveLotsBatch: vi.fn(),
  },
}));

import { accountsApi } from "../../api/accounts";

const baseLot: HoldingLot = {
  id: "lot-1",
  account_id: "acc-1",
  security_id: "sec-1",
  ticker: "AAPL",
  acquisition_date: "2025-01-15",
  cost_basis_per_unit: 150,
  original_quantity: 100,
  current_quantity: 100,
  is_closed: false,
  source: "manual",
  activity_id: null,
  total_cost_basis: 15000,
  unrealized_gain_loss: null,
  unrealized_gain_loss_percent: null,
  security_name: "Apple Inc.",
  disposals: [],
  created_at: "2025-01-15T00:00:00Z",
  updated_at: "2025-01-15T00:00:00Z",
};

const defaultProps = {
  isOpen: true,
  lot: null as HoldingLot | null,
  accountId: "acc-1",
  securityId: "sec-1",
  ticker: "AAPL",
  holdingQuantity: 100,
  otherLots: [] as HoldingLot[],
  onClose: vi.fn(),
  onSaved: vi.fn(),
};

describe("LotFormModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows remainder row when quantity is reduced below holding", () => {
    render(
      <LotFormModal
        {...defaultProps}
        lot={baseLot}
        otherLots={[]}
      />,
    );

    // Change quantity from 100 to 60
    const qtyInput = screen.getByTestId("lot-quantity");
    fireEvent.change(qtyInput, { target: { value: "60" } });

    // Remainder row should appear (100 - 60 = 40)
    expect(screen.getByTestId("remainder-row")).toBeInTheDocument();
    expect(screen.getByText(/40/)).toBeInTheDocument();
  });

  it("shows error when lot total would exceed holding quantity", () => {
    render(
      <LotFormModal
        {...defaultProps}
        lot={baseLot}
        otherLots={[]}
      />,
    );

    // Change quantity from 100 to 110
    const qtyInput = screen.getByTestId("lot-quantity");
    fireEvent.change(qtyInput, { target: { value: "110" } });

    expect(screen.getByTestId("lot-exceeds-error")).toBeInTheDocument();
    expect(screen.getByText(/exceed holding quantity/)).toBeInTheDocument();
  });

  it("does not show remainder when quantity matches holding", () => {
    render(
      <LotFormModal
        {...defaultProps}
        lot={baseLot}
        otherLots={[]}
      />,
    );

    // Quantity is already 100 which matches holding
    expect(screen.queryByTestId("remainder-row")).not.toBeInTheDocument();
    expect(screen.queryByTestId("lot-exceeds-error")).not.toBeInTheDocument();
  });

  it("accounts for other lots in remainder calculation", () => {
    const otherLot: HoldingLot = {
      ...baseLot,
      id: "lot-2",
      current_quantity: 30,
    };

    render(
      <LotFormModal
        {...defaultProps}
        lot={baseLot}
        otherLots={[otherLot]}
      />,
    );

    // Holding = 100, other lots = 30, editing lot set to 50
    // Remainder = 100 - 30 - 50 = 20
    const qtyInput = screen.getByTestId("lot-quantity");
    fireEvent.change(qtyInput, { target: { value: "50" } });

    expect(screen.getByTestId("remainder-row")).toBeInTheDocument();
    expect(screen.getByText(/20/)).toBeInTheDocument();
  });

  it("calls batch API when saving with remainder", async () => {
    vi.mocked(accountsApi.saveLotsBatch).mockResolvedValue({ data: [] } as never);

    render(
      <LotFormModal
        {...defaultProps}
        lot={baseLot}
        otherLots={[]}
      />,
    );

    // Reduce quantity to 60 (remainder = 40)
    fireEvent.change(screen.getByTestId("lot-quantity"), {
      target: { value: "60" },
    });

    // Fill in remainder fields
    fireEvent.change(screen.getByTestId("remainder-acquisition-date"), {
      target: { value: "2025-06-01" },
    });
    fireEvent.change(screen.getByTestId("remainder-cost-basis"), {
      target: { value: "170" },
    });

    // Submit
    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(accountsApi.saveLotsBatch).toHaveBeenCalledWith(
        "acc-1",
        "sec-1",
        {
          updates: [
            {
              id: "lot-1",
              acquisition_date: "2025-01-15",
              cost_basis_per_unit: 150,
              quantity: 60,
            },
          ],
          creates: [
            {
              ticker: "AAPL",
              acquisition_date: "2025-06-01",
              cost_basis_per_unit: 170,
              quantity: 40,
            },
          ],
        },
      );
    });
  });

  it("calls single update API when no remainder", async () => {
    vi.mocked(accountsApi.updateLot).mockResolvedValue({ data: baseLot } as never);

    render(
      <LotFormModal
        {...defaultProps}
        lot={baseLot}
        otherLots={[]}
      />,
    );

    // Change cost basis only (quantity stays at 100, matches holding)
    fireEvent.change(screen.getByTestId("lot-cost-basis"), {
      target: { value: "160" },
    });

    fireEvent.click(screen.getByText("Save"));

    await waitFor(() => {
      expect(accountsApi.updateLot).toHaveBeenCalledWith("acc-1", "lot-1", {
        acquisition_date: "2025-01-15",
        cost_basis_per_unit: 160,
        quantity: 100,
      });
    });
    expect(accountsApi.saveLotsBatch).not.toHaveBeenCalled();
  });

  it("does not show remainder when holdingQuantity is not provided", () => {
    render(
      <LotFormModal
        {...defaultProps}
        holdingQuantity={undefined}
        lot={baseLot}
        otherLots={[]}
      />,
    );

    // Change quantity
    fireEvent.change(screen.getByTestId("lot-quantity"), {
      target: { value: "50" },
    });

    expect(screen.queryByTestId("remainder-row")).not.toBeInTheDocument();
    expect(screen.queryByTestId("lot-exceeds-error")).not.toBeInTheDocument();
  });

  it("disables save button when lot exceeds holding", () => {
    render(
      <LotFormModal
        {...defaultProps}
        lot={baseLot}
        otherLots={[]}
      />,
    );

    fireEvent.change(screen.getByTestId("lot-quantity"), {
      target: { value: "110" },
    });

    const saveBtn = screen.getByText("Save");
    expect(saveBtn).toBeDisabled();
  });
});
