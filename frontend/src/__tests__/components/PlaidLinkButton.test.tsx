import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PlaidLinkButton } from "../../components/settings/PlaidLinkButton";

// Mock react-plaid-link
const mockOpen = vi.fn();
vi.mock("react-plaid-link", () => ({
  usePlaidLink: vi.fn(() => ({
    open: mockOpen,
    ready: false,
  })),
}));

// Mock plaid API
vi.mock("../../api/plaid", () => ({
  plaidApi: {
    createLinkToken: vi.fn(),
    exchangeToken: vi.fn(),
  },
}));

import { plaidApi } from "../../api/plaid";
import { usePlaidLink } from "react-plaid-link";

const mockedCreateLinkToken = vi.mocked(plaidApi.createLinkToken);
const mockedUsePlaidLink = vi.mocked(usePlaidLink);

describe("PlaidLinkButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUsePlaidLink.mockReturnValue({
      open: mockOpen,
      ready: false,
      exit: vi.fn(),
      submit: vi.fn(),
      error: null,
    });
  });

  it("renders Link Institution button", () => {
    render(<PlaidLinkButton />);
    expect(screen.getByText("Link Institution")).toBeInTheDocument();
  });

  it("fetches link token on click", async () => {
    mockedCreateLinkToken.mockResolvedValue({
      data: { link_token: "link-sandbox-test" },
    } as never);

    render(<PlaidLinkButton />);

    fireEvent.click(screen.getByText("Link Institution"));

    await waitFor(() => {
      expect(mockedCreateLinkToken).toHaveBeenCalled();
    });
  });

  it("shows error when link token creation fails", async () => {
    mockedCreateLinkToken.mockRejectedValue(new Error("API error"));

    render(<PlaidLinkButton />);

    fireEvent.click(screen.getByText("Link Institution"));

    await waitFor(() => {
      expect(screen.getByText("Failed to create link token")).toBeInTheDocument();
    });
  });
});
