import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AllocationFilterToggle } from "@/components/dashboard/AllocationFilterToggle";

describe("AllocationFilterToggle", () => {
  it("renders the toggle label", () => {
    render(<AllocationFilterToggle enabled={false} onChange={vi.fn()} />);
    expect(screen.getByText("Allocation accounts only")).toBeInTheDocument();
  });

  it("calls onChange with true when toggled on", () => {
    const onChange = vi.fn();
    render(<AllocationFilterToggle enabled={false} onChange={onChange} />);

    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("calls onChange with false when toggled off", () => {
    const onChange = vi.fn();
    render(<AllocationFilterToggle enabled={true} onChange={onChange} />);

    const checkbox = screen.getByRole("checkbox");
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("reflects enabled state visually", () => {
    const { rerender } = render(
      <AllocationFilterToggle enabled={false} onChange={vi.fn()} />
    );

    // When disabled, the track should be gray
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).not.toBeChecked();

    // When enabled, the track should be blue
    rerender(<AllocationFilterToggle enabled={true} onChange={vi.fn()} />);
    expect(checkbox).toBeChecked();
  });
});
