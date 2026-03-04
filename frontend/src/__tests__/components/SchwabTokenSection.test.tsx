import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { SchwabTokenSection } from "../../components/settings/SchwabTokenSection";

vi.mock("../../api/schwab", () => ({
  schwabApi: {
    getTokenStatus: vi.fn(),
    createAuthUrl: vi.fn(),
    exchangeToken: vi.fn(),
  },
}));

import { schwabApi } from "../../api/schwab";

const mockedGetTokenStatus = vi.mocked(schwabApi.getTokenStatus);
const mockedCreateAuthUrl = vi.mocked(schwabApi.createAuthUrl);
const mockedExchangeToken = vi.mocked(schwabApi.exchangeToken);

describe("SchwabTokenSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when no_credentials", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_credentials", message: "Not configured.", days_remaining: null },
    } as never);

    const { container } = render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(mockedGetTokenStatus).toHaveBeenCalled();
    });

    // Should render nothing
    expect(container.innerHTML).toBe("");
  });

  it("shows Not Authorized badge and Authorize button when no_token", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_token", message: "No token found.", days_remaining: null },
    } as never);

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByText("Not Authorized")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "Authorize" })).toBeInTheDocument();
  });

  it("shows Token Valid badge with days remaining when valid", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "valid", message: "Valid.", days_remaining: 5.3 },
    } as never);

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByText("Token Valid")).toBeInTheDocument();
    });

    expect(screen.getByText("5.3 days remaining")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-authorize" })).toBeInTheDocument();
  });

  it("shows warning when expiring_soon", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: {
        status: "expiring_soon",
        message: "Schwab token expires in 1.5 days.",
        expires_at: null,
        days_remaining: 1.5,
      },
    } as never);

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByText("Expiring Soon")).toBeInTheDocument();
    });

    expect(screen.getByText("Schwab token expires in 1.5 days.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-authorize" })).toBeInTheDocument();
  });

  it("shows error when expired", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: {
        status: "expired",
        message: "Schwab token has expired.",
        expires_at: null,
        days_remaining: 0,
      },
    } as never);

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByText("Token Expired")).toBeInTheDocument();
    });

    expect(screen.getByText("Schwab token has expired.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Authorize" })).toBeInTheDocument();
  });

  it("clicking Authorize calls createAuthUrl and opens window", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_token", message: "No token.", days_remaining: null },
    } as never);
    mockedCreateAuthUrl.mockResolvedValue({
      data: { authorization_url: "https://schwab.example.com/auth", state: "state123" },
    } as never);

    const mockWindow = { location: { href: "" }, close: vi.fn() };
    const mockOpen = vi.fn().mockReturnValue(mockWindow);
    vi.stubGlobal("open", mockOpen);

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Authorize" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Authorize" }));

    await waitFor(() => {
      expect(mockedCreateAuthUrl).toHaveBeenCalled();
      expect(mockOpen).toHaveBeenCalledWith("about:blank", "_blank");
      expect(mockWindow.location.href).toBe("https://schwab.example.com/auth");
    });

    // Paste flow should be visible
    expect(screen.getByPlaceholderText("Paste redirect URL here...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Complete Authorization" })).toBeInTheDocument();
  });

  it("paste flow calls exchangeToken on submit", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_token", message: "No token.", days_remaining: null },
    } as never);
    mockedCreateAuthUrl.mockResolvedValue({
      data: { authorization_url: "https://schwab.example.com/auth", state: "state123" },
    } as never);
    mockedExchangeToken.mockResolvedValue({
      data: { message: "Success! Found 2 account(s).", account_count: 2 },
    } as never);

    // After exchange, re-fetch shows valid
    mockedGetTokenStatus
      .mockResolvedValueOnce({
        data: { status: "no_token", message: "No token.", days_remaining: null },
      } as never)
      .mockResolvedValueOnce({
        data: { status: "valid", message: "Valid.", days_remaining: 6.8 },
      } as never);

    vi.stubGlobal("open", vi.fn().mockReturnValue({ location: { href: "" }, close: vi.fn() }));

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Authorize" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Authorize" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Paste redirect URL here...")).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText("Paste redirect URL here...");
    fireEvent.change(input, { target: { value: "https://127.0.0.1?code=abc&session=state123" } });

    fireEvent.click(screen.getByRole("button", { name: "Complete Authorization" }));

    await waitFor(() => {
      expect(mockedExchangeToken).toHaveBeenCalledWith(
        "state123",
        "https://127.0.0.1?code=abc&session=state123",
      );
    });
  });

  it("auto-detects callback completion via polling", async () => {
    // Initial status: no token
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_token", message: "No token.", days_remaining: null },
    } as never);
    mockedCreateAuthUrl.mockResolvedValue({
      data: { authorization_url: "https://schwab.example.com/auth", state: "state123" },
    } as never);

    vi.stubGlobal("open", vi.fn().mockReturnValue({ location: { href: "" }, close: vi.fn() }));

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Authorize" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Authorize" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Paste redirect URL here...")).toBeInTheDocument();
    });

    // Simulate callback completing — next poll returns valid
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "valid", message: "Valid.", days_remaining: 6.9 },
    } as never);

    // Wait for the polling interval (3s) to detect the new token
    await waitFor(
      () => {
        expect(screen.getByText(/authorized successfully via callback/i)).toBeInTheDocument();
      },
      { timeout: 5000 },
    );

    // Paste flow should be dismissed
    expect(screen.queryByPlaceholderText("Paste redirect URL here...")).not.toBeInTheDocument();
  }, 10000);

  it("shows error message on exchange failure", async () => {
    mockedGetTokenStatus.mockResolvedValue({
      data: { status: "no_token", message: "No token.", days_remaining: null },
    } as never);
    mockedCreateAuthUrl.mockResolvedValue({
      data: { authorization_url: "https://schwab.example.com/auth", state: "state123" },
    } as never);
    mockedExchangeToken.mockRejectedValue({
      response: { data: { detail: "Token exchange failed: invalid code" } },
    });

    vi.stubGlobal("open", vi.fn().mockReturnValue({ location: { href: "" }, close: vi.fn() }));

    render(<SchwabTokenSection />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Authorize" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Authorize" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Paste redirect URL here...")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Paste redirect URL here..."), {
      target: { value: "https://127.0.0.1?code=bad" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Complete Authorization" }));

    await waitFor(() => {
      expect(screen.getByText("Token exchange failed: invalid code")).toBeInTheDocument();
    });
  });
});
