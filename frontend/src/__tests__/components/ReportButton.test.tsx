import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ReportButton } from "../../components/dashboard/ReportButton";

describe("ReportButton", () => {
  it("renders report button", () => {
    const mockClick = vi.fn();
    render(<ReportButton onClick={mockClick} />);

    const button = screen.getByRole("button", { name: /report/i });
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  it("calls onClick when clicked", () => {
    const mockClick = vi.fn();
    render(<ReportButton onClick={mockClick} />);

    const button = screen.getByRole("button", { name: /report/i });
    fireEvent.click(button);

    expect(mockClick).toHaveBeenCalled();
  });
});
