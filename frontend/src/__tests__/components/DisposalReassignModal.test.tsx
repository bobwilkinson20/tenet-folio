import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { DisposalReassignModal } from "../../components/lots/DisposalReassignModal";

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    getLotsBySecurity: vi.fn(),
    reassignDisposals: vi.fn(),
  },
}));

import { accountsApi } from "../../api/accounts";

const mockLots = [
  {
    id: "lot-1",
    account_id: "acc-1",
    security_id: "sec-1",
    ticker: "AAPL",
    acquisition_date: "2025-01-15",
    cost_basis_per_unit: 150,
    original_quantity: 50,
    current_quantity: 50,
    is_closed: false,
    source: "manual" as const,
    activity_id: null,
    total_cost_basis: 7500,
    unrealized_gain_loss: null,
    unrealized_gain_loss_percent: null,
    security_name: "Apple Inc.",
    disposals: [],
    created_at: "2025-01-15T00:00:00Z",
    updated_at: "2025-01-15T00:00:00Z",
  },
  {
    id: "lot-2",
    account_id: "acc-1",
    security_id: "sec-1",
    ticker: "AAPL",
    acquisition_date: "2025-03-01",
    cost_basis_per_unit: 170,
    original_quantity: 30,
    current_quantity: 30,
    is_closed: false,
    source: "manual" as const,
    activity_id: null,
    total_cost_basis: 5100,
    unrealized_gain_loss: null,
    unrealized_gain_loss_percent: null,
    security_name: "Apple Inc.",
    disposals: [],
    created_at: "2025-03-01T00:00:00Z",
    updated_at: "2025-03-01T00:00:00Z",
  },
];

const defaultProps = {
  isOpen: true,
  accountId: "acc-1",
  securityId: "sec-1",
  disposalGroupId: "dg-1",
  totalQuantity: 20,
  disposalDate: "2025-06-15",
  proceedsPerUnit: 200,
  onClose: vi.fn(),
  onSaved: vi.fn(),
};

describe("DisposalReassignModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders available lots for reassignment", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: mockLots,
    } as never);

    render(<DisposalReassignModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("reassign-lots-table")).toBeInTheDocument();
    });

    expect(screen.getByText("2025-01-15")).toBeInTheDocument();
    expect(screen.getByText("2025-03-01")).toBeInTheDocument();
    expect(screen.getByTestId("reassign-qty-lot-1")).toBeInTheDocument();
    expect(screen.getByTestId("reassign-qty-lot-2")).toBeInTheDocument();
  });

  it("shows remaining quantity calculation", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: mockLots,
    } as never);

    render(<DisposalReassignModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("reassign-lots-table")).toBeInTheDocument();
    });

    // Initially remaining should equal total
    expect(screen.getByText("Remaining: 20.0000")).toBeInTheDocument();

    // Assign 10 to lot-1
    fireEvent.change(screen.getByTestId("reassign-qty-lot-1"), {
      target: { value: "10" },
    });

    expect(screen.getByText("Remaining: 10.0000")).toBeInTheDocument();
  });

  it("submits reassignment when total matches", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: mockLots,
    } as never);
    vi.mocked(accountsApi.reassignDisposals).mockResolvedValue({
      data: [],
    } as never);

    render(<DisposalReassignModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("reassign-lots-table")).toBeInTheDocument();
    });

    // Assign 15 to lot-1 and 5 to lot-2 (total = 20)
    fireEvent.change(screen.getByTestId("reassign-qty-lot-1"), {
      target: { value: "15" },
    });
    fireEvent.change(screen.getByTestId("reassign-qty-lot-2"), {
      target: { value: "5" },
    });

    fireEvent.click(screen.getByText("Reassign"));

    await waitFor(() => {
      expect(accountsApi.reassignDisposals).toHaveBeenCalledWith(
        "acc-1",
        "dg-1",
        {
          assignments: [
            { lot_id: "lot-1", quantity: 15 },
            { lot_id: "lot-2", quantity: 5 },
          ],
        },
      );
    });
  });

  it("shows error when total does not match", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: mockLots,
    } as never);

    render(<DisposalReassignModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("reassign-lots-table")).toBeInTheDocument();
    });

    // Assign only 10 (total needed is 20)
    fireEvent.change(screen.getByTestId("reassign-qty-lot-1"), {
      target: { value: "10" },
    });

    fireEvent.click(screen.getByText("Reassign"));

    await waitFor(() => {
      expect(screen.getByTestId("reassign-error")).toBeInTheDocument();
    });

    expect(screen.getByText(/Total assigned quantity must equal 20/)).toBeInTheDocument();
  });

  it("shows empty state when no open lots", async () => {
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [],
    } as never);

    render(<DisposalReassignModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText(/No open lots available/)).toBeInTheDocument();
    });
  });

  it("filters out closed lots", async () => {
    const closedLot = {
      ...mockLots[0],
      id: "lot-closed",
      is_closed: true,
      current_quantity: 0,
    };
    vi.mocked(accountsApi.getLotsBySecurity).mockResolvedValue({
      data: [closedLot, mockLots[1]],
    } as never);

    render(<DisposalReassignModal {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByTestId("reassign-lots-table")).toBeInTheDocument();
    });

    // Only lot-2 should be visible (lot-closed is closed)
    expect(screen.queryByTestId("reassign-qty-lot-closed")).not.toBeInTheDocument();
    expect(screen.getByTestId("reassign-qty-lot-2")).toBeInTheDocument();
  });
});
