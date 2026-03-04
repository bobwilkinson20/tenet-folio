import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PlaidUpdateButton } from "../../components/settings/PlaidUpdateButton";

// Mock react-plaid-link
const mockOpen = vi.fn();
vi.mock("react-plaid-link", () => ({
  usePlaidLink: vi.fn(() => ({
    open: mockOpen,
    ready: true,
    exit: vi.fn(),
    error: null,
  })),
}));

// Mock plaid API
vi.mock("../../api/plaid", () => ({
  plaidApi: {
    createUpdateLinkToken: vi.fn(),
    clearItemError: vi.fn(),
  },
}));

import { plaidApi } from "../../api/plaid";

const mockedCreateUpdateLinkToken = vi.mocked(plaidApi.createUpdateLinkToken);

describe("PlaidUpdateButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Update button", () => {
    render(<PlaidUpdateButton itemId="item-1" />);
    expect(screen.getByText("Update")).toBeInTheDocument();
  });

  it("fetches update link token on click", async () => {
    mockedCreateUpdateLinkToken.mockResolvedValue({
      data: { link_token: "link-update-token" },
    } as never);

    render(<PlaidUpdateButton itemId="item-1" />);

    fireEvent.click(screen.getByText("Update"));

    await waitFor(() => {
      expect(mockedCreateUpdateLinkToken).toHaveBeenCalledWith("item-1");
    });
  });

  it("shows error on failure", async () => {
    mockedCreateUpdateLinkToken.mockRejectedValue(new Error("API error"));

    render(<PlaidUpdateButton itemId="item-1" />);

    fireEvent.click(screen.getByText("Update"));

    await waitFor(() => {
      expect(
        screen.getByText("Failed to start update"),
      ).toBeInTheDocument();
    });
  });
});
