import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PlaidItemList } from "../../components/settings/PlaidItemList";

// Mock react-plaid-link (needed by PlaidLinkButton child)
vi.mock("react-plaid-link", () => ({
  usePlaidLink: vi.fn(() => ({
    open: vi.fn(),
    ready: false,
    exit: vi.fn(),
    error: null,
  })),
}));

// Mock plaid API
vi.mock("../../api/plaid", () => ({
  plaidApi: {
    createLinkToken: vi.fn(),
    exchangeToken: vi.fn(),
    listItems: vi.fn(),
    removeItem: vi.fn(),
  },
}));

import { plaidApi } from "../../api/plaid";

const mockedListItems = vi.mocked(plaidApi.listItems);
const mockedRemoveItem = vi.mocked(plaidApi.removeItem);

const sampleItems = [
  {
    id: "uuid-1",
    item_id: "item-1",
    institution_id: "ins_1",
    institution_name: "Chase",
    created_at: "2026-01-15T10:00:00Z",
  },
  {
    id: "uuid-2",
    item_id: "item-2",
    institution_id: "ins_2",
    institution_name: "Vanguard",
    created_at: "2026-01-20T12:00:00Z",
  },
];

describe("PlaidItemList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedListItems.mockResolvedValue({ data: sampleItems } as never);
  });

  it("renders linked institutions", async () => {
    render(<PlaidItemList />);

    await waitFor(() => {
      expect(screen.getByText("Chase")).toBeInTheDocument();
    });

    expect(screen.getByText("Vanguard")).toBeInTheDocument();
  });

  it("shows empty state when no items", async () => {
    mockedListItems.mockResolvedValue({ data: [] } as never);

    render(<PlaidItemList />);

    await waitFor(() => {
      expect(
        screen.getByText(/No institutions linked yet/),
      ).toBeInTheDocument();
    });
  });

  it("removes an item when Remove is clicked", async () => {
    mockedRemoveItem.mockResolvedValue({ data: { status: "ok" } } as never);

    render(<PlaidItemList />);

    await waitFor(() => {
      expect(screen.getByText("Chase")).toBeInTheDocument();
    });

    const removeButtons = screen.getAllByText("Remove");
    fireEvent.click(removeButtons[0]);

    await waitFor(() => {
      expect(mockedRemoveItem).toHaveBeenCalledWith("item-1");
    });
  });

  it("renders Link Institution button", async () => {
    render(<PlaidItemList />);

    await waitFor(() => {
      expect(screen.getByText("Link Institution")).toBeInTheDocument();
    });
  });
});
