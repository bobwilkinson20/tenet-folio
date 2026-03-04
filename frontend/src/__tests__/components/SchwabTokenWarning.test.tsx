import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SchwabTokenWarning } from "../../components/dashboard/SchwabTokenWarning";

vi.mock("../../api/schwab", () => ({
  schwabApi: {
    getTokenStatus: vi.fn(),
  },
}));

import { schwabApi } from "../../api/schwab";

const mockedGetTokenStatus = vi.mocked(schwabApi.getTokenStatus);

describe("SchwabTokenWarning", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when valid", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "valid", message: "Valid.", expires_at: null, days_remaining: 5.0 },
    } as never);

    const { container } = render(<SchwabTokenWarning />);

    await waitFor(() => {
      expect(mockedGetTokenStatus).toHaveBeenCalled();
    });

    // Allow time for state update
    await waitFor(() => {
      expect(container.querySelector("[data-testid='schwab-token-warning']")).toBeNull();
    });
  });

  it("renders nothing when no_credentials", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_credentials", message: "Not configured.", expires_at: null, days_remaining: null },
    } as never);

    const { container } = render(<SchwabTokenWarning />);

    await waitFor(() => {
      expect(mockedGetTokenStatus).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(container.querySelector("[data-testid='schwab-token-warning']")).toBeNull();
    });
  });

  it("renders nothing when no_token", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_token", message: "No token.", expires_at: null, days_remaining: null },
    } as never);

    const { container } = render(<SchwabTokenWarning />);

    await waitFor(() => {
      expect(mockedGetTokenStatus).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(container.querySelector("[data-testid='schwab-token-warning']")).toBeNull();
    });
  });

  it("shows amber banner for expiring_soon", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: {
        status: "expiring_soon",
        message: "Schwab token expires in 1.5 days.",
        expires_at: null,
        days_remaining: 1.5,
      },
    } as never);

    render(<SchwabTokenWarning />);

    await waitFor(() => {
      expect(screen.getByTestId("schwab-token-warning")).toBeInTheDocument();
    });

    expect(screen.getByText("Schwab token expiring soon")).toBeInTheDocument();
    expect(screen.getByText(/Schwab token expires in 1.5 days/)).toBeInTheDocument();
    expect(screen.getByText("Go to Settings to re-authorize")).toBeInTheDocument();

    const banner = screen.getByTestId("schwab-token-warning");
    expect(banner.className).toContain("bg-tf-warning");
  });

  it("shows red banner for expired", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: {
        status: "expired",
        message: "Schwab token has expired.",
        expires_at: null,
        days_remaining: 0,
      },
    } as never);

    render(<SchwabTokenWarning />);

    await waitFor(() => {
      expect(screen.getByTestId("schwab-token-warning")).toBeInTheDocument();
    });

    expect(screen.getByText("Schwab token expired")).toBeInTheDocument();
    expect(screen.getByText(/Schwab token has expired/)).toBeInTheDocument();
    expect(screen.getByText("Go to Settings to re-authorize")).toBeInTheDocument();

    const banner = screen.getByTestId("schwab-token-warning");
    expect(banner.className).toContain("bg-tf-negative");
  });

  it("banner contains link to settings", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: {
        status: "expiring_soon",
        message: "Expiring.",
        expires_at: null,
        days_remaining: 1.0,
      },
    } as never);

    render(<SchwabTokenWarning />);

    await waitFor(() => {
      expect(screen.getByTestId("schwab-token-warning")).toBeInTheDocument();
    });

    const link = screen.getByText("Go to Settings to re-authorize");
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).toBe("/settings");
  });
});
