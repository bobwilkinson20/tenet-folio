import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ActivityTable } from "../../components/cashflows/ActivityTable";
import type { Activity } from "../../types";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from "@/api/client";

const makeActivity = (overrides: Partial<Activity> = {}): Activity => ({
  id: "act-1",
  account_id: "acc-1",
  provider_name: "SnapTrade",
  external_id: "ext-1",
  activity_date: "2025-06-15T00:00:00Z",
  settlement_date: null,
  type: "deposit",
  description: "Wire transfer",
  ticker: null,
  units: null,
  price: null,
  amount: "5000.00",
  currency: "USD",
  fee: null,
  is_reviewed: false,
  notes: "Monthly",
  user_modified: false,
  created_at: "2025-06-15T12:00:00Z",
  ...overrides,
});

const defaultProps = {
  accountId: "acc-1",
  loading: false,
  onActivityUpdated: vi.fn(),
  onActivityDeleted: vi.fn(),
  onAddActivity: vi.fn(),
};

describe("ActivityTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders activity rows", () => {
    const activities = [
      makeActivity({ id: "act-1" }),
      makeActivity({ id: "act-2", type: "withdrawal", amount: "1000.00" }),
    ];
    render(<ActivityTable {...defaultProps} activities={activities} />);
    expect(screen.getByTestId("activity-row-act-1")).toBeInTheDocument();
    expect(screen.getByTestId("activity-row-act-2")).toBeInTheDocument();
  });

  it("renders loading state", () => {
    render(<ActivityTable {...defaultProps} activities={[]} loading={true} />);
    expect(screen.getByText("Loading activities...")).toBeInTheDocument();
  });

  it("renders empty state", () => {
    render(<ActivityTable {...defaultProps} activities={[]} />);
    expect(screen.getByText("No activities found.")).toBeInTheDocument();
  });

  describe("type cell editing", () => {
    it("opens select on click and saves on change", async () => {
      const updatedActivity = makeActivity({ type: "withdrawal", user_modified: true });
      vi.mocked(apiClient.patch).mockResolvedValue({ data: updatedActivity });

      render(
        <ActivityTable {...defaultProps} activities={[makeActivity()]} />,
      );

      // Click the type cell to open select
      fireEvent.click(screen.getByTestId("type-cell-act-1"));
      const select = screen.getByTestId("edit-type");
      expect(select).toBeInTheDocument();

      // Change the value
      fireEvent.change(select, { target: { value: "withdrawal" } });

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalledWith(
          "/accounts/acc-1/activities/act-1",
          { type: "withdrawal" },
        );
      });
      expect(defaultProps.onActivityUpdated).toHaveBeenCalledWith(updatedActivity);
    });

    it("does not call API when same value selected", async () => {
      render(
        <ActivityTable {...defaultProps} activities={[makeActivity()]} />,
      );

      fireEvent.click(screen.getByTestId("type-cell-act-1"));
      const select = screen.getByTestId("edit-type");

      // Select same value
      fireEvent.change(select, { target: { value: "deposit" } });

      // Wait a tick to ensure no call
      await new Promise((r) => setTimeout(r, 50));
      expect(apiClient.patch).not.toHaveBeenCalled();
    });
  });

  describe("amount cell editing", () => {
    it("opens input on click and saves on blur with new value", async () => {
      const user = userEvent.setup();
      const updatedActivity = makeActivity({ amount: "9999.00", user_modified: true });
      vi.mocked(apiClient.patch).mockResolvedValue({ data: updatedActivity });

      render(
        <ActivityTable {...defaultProps} activities={[makeActivity()]} />,
      );

      // Click the amount cell
      fireEvent.click(screen.getByTestId("amount-cell-act-1"));
      const input = screen.getByTestId("edit-amount");
      expect(input).toBeInTheDocument();

      // Clear and type new value
      await user.clear(input);
      await user.type(input, "9999");
      fireEvent.blur(input);

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalledWith(
          "/accounts/acc-1/activities/act-1",
          { amount: 9999 },
        );
      });
    });

    it("does not call API when blurring with same value", async () => {
      render(
        <ActivityTable {...defaultProps} activities={[makeActivity()]} />,
      );

      fireEvent.click(screen.getByTestId("amount-cell-act-1"));
      const input = screen.getByTestId("edit-amount");

      // Blur without changing
      fireEvent.blur(input);

      await new Promise((r) => setTimeout(r, 50));
      expect(apiClient.patch).not.toHaveBeenCalled();
    });

  });

  describe("notes cell editing", () => {
    it("saves on blur with new value", async () => {
      const user = userEvent.setup();
      const updatedActivity = makeActivity({ notes: "Updated note" });
      vi.mocked(apiClient.patch).mockResolvedValue({ data: updatedActivity });

      render(
        <ActivityTable {...defaultProps} activities={[makeActivity()]} />,
      );

      fireEvent.click(screen.getByTestId("notes-cell-act-1"));
      const input = screen.getByTestId("edit-notes");

      await user.clear(input);
      await user.type(input, "Updated note");
      fireEvent.blur(input);

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalledWith(
          "/accounts/acc-1/activities/act-1",
          { notes: "Updated note" },
        );
      });
    });
  });

  describe("date cell", () => {
    it("is editable for manual activities", () => {
      const manualActivity = makeActivity({ provider_name: "Manual" });
      render(
        <ActivityTable {...defaultProps} activities={[manualActivity]} />,
      );

      const dateCell = screen.getByTestId("date-cell-act-1");
      fireEvent.click(dateCell);

      expect(screen.getByTestId("edit-date")).toBeInTheDocument();
    });

    it("is NOT editable for synced activities", () => {
      const syncedActivity = makeActivity({ provider_name: "SnapTrade" });
      render(
        <ActivityTable {...defaultProps} activities={[syncedActivity]} />,
      );

      const dateCell = screen.getByTestId("date-cell-act-1");
      fireEvent.click(dateCell);

      expect(screen.queryByTestId("edit-date")).not.toBeInTheDocument();
    });

    it("saves on blur with new date for manual activities", async () => {
      const updatedActivity = makeActivity({
        provider_name: "Manual",
        activity_date: "2025-07-01T00:00:00Z",
      });
      vi.mocked(apiClient.patch).mockResolvedValue({ data: updatedActivity });

      render(
        <ActivityTable
          {...defaultProps}
          activities={[makeActivity({ provider_name: "Manual" })]}
        />,
      );

      fireEvent.click(screen.getByTestId("date-cell-act-1"));
      const input = screen.getByTestId("edit-date");

      fireEvent.change(input, { target: { value: "2025-07-01" } });
      fireEvent.blur(input);

      await waitFor(() => {
        expect(apiClient.patch).toHaveBeenCalledWith(
          "/accounts/acc-1/activities/act-1",
          { activity_date: "2025-07-01T00:00:00Z" },
        );
      });
    });
  });

  describe("delete button", () => {
    it("is shown only for manual activities", () => {
      const activities = [
        makeActivity({ id: "manual-1", provider_name: "Manual" }),
        makeActivity({ id: "synced-1", provider_name: "SnapTrade" }),
      ];
      render(<ActivityTable {...defaultProps} activities={activities} />);

      expect(screen.getByTestId("delete-btn-manual-1")).toBeInTheDocument();
      expect(screen.queryByTestId("delete-btn-synced-1")).not.toBeInTheDocument();
    });

    it("calls API and triggers callback on confirm", async () => {
      vi.mocked(apiClient.delete).mockResolvedValue({ data: null });
      vi.spyOn(window, "confirm").mockReturnValue(true);

      const manualActivity = makeActivity({ provider_name: "Manual" });
      render(
        <ActivityTable {...defaultProps} activities={[manualActivity]} />,
      );

      fireEvent.click(screen.getByTestId("delete-btn-act-1"));

      await waitFor(() => {
        expect(apiClient.delete).toHaveBeenCalledWith(
          "/accounts/acc-1/activities/act-1",
        );
      });
      expect(defaultProps.onActivityDeleted).toHaveBeenCalled();
    });

    it("does not call API when confirm is cancelled", async () => {
      vi.spyOn(window, "confirm").mockReturnValue(false);

      const manualActivity = makeActivity({ provider_name: "Manual" });
      render(
        <ActivityTable {...defaultProps} activities={[manualActivity]} />,
      );

      fireEvent.click(screen.getByTestId("delete-btn-act-1"));

      await new Promise((r) => setTimeout(r, 50));
      expect(apiClient.delete).not.toHaveBeenCalled();
    });
  });

  it("does not show Save/Cancel buttons", () => {
    render(
      <ActivityTable {...defaultProps} activities={[makeActivity()]} />,
    );

    expect(screen.queryByTestId("edit-save")).not.toBeInTheDocument();
    expect(screen.queryByTestId("edit-cancel")).not.toBeInTheDocument();
  });
});
