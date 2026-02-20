import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SyncButton } from "../../components/dashboard/SyncButton";

describe("SyncButton", () => {
  it("renders sync button", () => {
    const mockSync = vi.fn();
    render(<SyncButton onSync={mockSync} syncing={false} />);

    const button = screen.getByRole("button", { name: /sync now/i });
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  it("calls onSync when clicked", async () => {
    const mockSync = vi.fn().mockResolvedValue(undefined);
    render(<SyncButton onSync={mockSync} syncing={false} />);

    const button = screen.getByRole("button", { name: /sync now/i });
    fireEvent.click(button);

    expect(mockSync).toHaveBeenCalled();
  });

  it("shows syncing state when syncing prop is true", () => {
    const mockSync = vi.fn();
    render(<SyncButton onSync={mockSync} syncing={true} />);

    expect(screen.getByRole("button", { name: /syncing/i })).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("shows sync now when syncing prop is false", () => {
    const mockSync = vi.fn();
    render(<SyncButton onSync={mockSync} syncing={false} />);

    expect(screen.getByRole("button", { name: /sync now/i })).toBeInTheDocument();
    expect(screen.getByRole("button")).not.toBeDisabled();
  });

  it("does not call onSync when already syncing", async () => {
    const mockSync = vi.fn();
    render(<SyncButton onSync={mockSync} syncing={true} />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockSync).not.toHaveBeenCalled();
    });
  });
});
