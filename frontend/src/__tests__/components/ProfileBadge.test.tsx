import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProfileBadge } from "../../components/layout/ProfileBadge";
import { apiClient } from "@/api/client";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

describe("ProfileBadge", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
  });

  it("renders nothing when API returns null profile", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { profile: null } });
    const { container } = render(<ProfileBadge />);
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith("/config/profile");
    });
    expect(container.firstChild).toBeNull();
  });

  it("renders badge text when API returns a profile name", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { profile: "paper" } });
    render(<ProfileBadge />);
    await waitFor(() => {
      expect(screen.getByText("paper")).toBeInTheDocument();
    });
  });

  it("renders nothing on API error", async () => {
    vi.mocked(apiClient.get).mockRejectedValue(new Error("Network error"));
    const { container } = render(<ProfileBadge />);
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalled();
    });
    expect(container.firstChild).toBeNull();
  });
});
