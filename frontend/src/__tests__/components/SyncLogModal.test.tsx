import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SyncLogModal } from "../../components/dashboard/SyncLogModal";
import type { SyncLogEntry } from "../../types/sync_session";

describe("SyncLogModal", () => {
  const mockClose = vi.fn();

  const sampleSyncLog: SyncLogEntry[] = [
    {
      id: "log-1",
      provider_name: "SnapTrade",
      status: "success",
      error_messages: null,
      accounts_synced: 2,
      created_at: "2026-01-29T12:00:00Z",
    },
    {
      id: "log-2",
      provider_name: "SimpleFIN",
      status: "failed",
      error_messages: ["Connection timeout"],
      accounts_synced: 0,
      created_at: "2026-01-29T12:00:00Z",
    },
  ];

  it("is hidden when not open", () => {
    render(
      <SyncLogModal
        isOpen={false}
        onClose={mockClose}
        syncing={false}
        syncLog={null}
        errorMessage={null}
      />
    );

    expect(screen.queryByTestId("sync-log-modal")).not.toBeInTheDocument();
  });

  it("shows loading state when syncing", () => {
    render(
      <SyncLogModal
        isOpen={true}
        onClose={mockClose}
        syncing={true}
        syncLog={null}
        errorMessage={null}
      />
    );

    expect(screen.getByTestId("sync-log-loading")).toBeInTheDocument();
    expect(screen.getByText(/syncing portfolios/i)).toBeInTheDocument();
  });

  it("shows provider results when sync completes", () => {
    render(
      <SyncLogModal
        isOpen={true}
        onClose={mockClose}
        syncing={false}
        syncLog={sampleSyncLog}
        errorMessage={null}
      />
    );

    expect(screen.getByTestId("sync-log-results")).toBeInTheDocument();
    expect(screen.getByText("SnapTrade")).toBeInTheDocument();
    expect(screen.getByText("SimpleFIN")).toBeInTheDocument();
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows error messages for failed providers", () => {
    render(
      <SyncLogModal
        isOpen={true}
        onClose={mockClose}
        syncing={false}
        syncLog={sampleSyncLog}
        errorMessage={null}
      />
    );

    expect(screen.getByText("Connection timeout")).toBeInTheDocument();
  });

  it("shows accounts synced count", () => {
    render(
      <SyncLogModal
        isOpen={true}
        onClose={mockClose}
        syncing={false}
        syncLog={sampleSyncLog}
        errorMessage={null}
      />
    );

    expect(screen.getByText("2 accounts synced")).toBeInTheDocument();
    expect(screen.getByText("0 accounts synced")).toBeInTheDocument();
  });

  it("shows generic error when no sync log available", () => {
    render(
      <SyncLogModal
        isOpen={true}
        onClose={mockClose}
        syncing={false}
        syncLog={null}
        errorMessage="Unexpected error occurred"
      />
    );

    expect(screen.getByTestId("sync-log-error")).toBeInTheDocument();
    expect(screen.getByText("Unexpected error occurred")).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    render(
      <SyncLogModal
        isOpen={true}
        onClose={mockClose}
        syncing={false}
        syncLog={sampleSyncLog}
        errorMessage={null}
      />
    );

    fireEvent.click(screen.getByTestId("sync-log-close"));
    expect(mockClose).toHaveBeenCalled();
  });
});
