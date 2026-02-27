import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ReportButton } from "../../components/dashboard/ReportButton";

describe("ReportButton", () => {
  it("renders report button", () => {
    const mockReport = vi.fn();
    render(<ReportButton onReport={mockReport} generating={false} />);

    const button = screen.getByRole("button", { name: /report/i });
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  it("calls onReport when clicked", async () => {
    const mockReport = vi.fn().mockResolvedValue(undefined);
    render(<ReportButton onReport={mockReport} generating={false} />);

    const button = screen.getByRole("button", { name: /report/i });
    fireEvent.click(button);

    expect(mockReport).toHaveBeenCalled();
  });

  it("shows generating state when generating prop is true", () => {
    const mockReport = vi.fn();
    render(<ReportButton onReport={mockReport} generating={true} />);

    expect(
      screen.getByRole("button", { name: /generating/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("does not call onReport when already generating", async () => {
    const mockReport = vi.fn();
    render(<ReportButton onReport={mockReport} generating={true} />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockReport).not.toHaveBeenCalled();
    });
  });
});
