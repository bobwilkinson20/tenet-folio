import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ActivityList } from "../../components/activities/ActivityList";
import type { Activity } from "../../types";

const makeActivity = (overrides: Partial<Activity> = {}): Activity => ({
  id: "act-1",
  account_id: "acc-1",
  provider_name: "SnapTrade",
  external_id: "ext-1",
  activity_date: "2025-06-15T00:00:00Z",
  settlement_date: null,
  type: "DIVIDEND",
  description: "Quarterly dividend payment",
  ticker: "VTI",
  units: null,
  price: null,
  amount: "125.50",
  currency: "USD",
  fee: null,
  is_reviewed: false,
  notes: null,
  user_modified: false,
  created_at: "2025-06-15T12:00:00Z",
  ...overrides,
});

describe("ActivityList", () => {
  it("renders loading state", () => {
    render(<ActivityList activities={[]} loading={true} />);
    expect(screen.getByText("Loading activity...")).toBeInTheDocument();
  });

  it("renders empty state when no activities", () => {
    render(<ActivityList activities={[]} loading={false} />);
    expect(screen.getByText("No activity found.")).toBeInTheDocument();
  });

  it("renders table headers", () => {
    render(<ActivityList activities={[makeActivity()]} loading={false} />);
    expect(screen.getByText("Date")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
    expect(screen.getByText("Description")).toBeInTheDocument();
    expect(screen.getByText("Amount")).toBeInTheDocument();
  });

  it("renders activity data", () => {
    render(<ActivityList activities={[makeActivity()]} loading={false} />);
    expect(screen.getByText("Dividend")).toBeInTheDocument();
    expect(screen.getByText("Quarterly dividend payment")).toBeInTheDocument();
  });

  it("formats the date using locale date string", () => {
    render(
      <ActivityList
        activities={[makeActivity({ activity_date: "2025-03-20T00:00:00Z" })]}
        loading={false}
      />,
    );
    const dateStr = new Date("2025-03-20T00:00:00Z").toLocaleDateString();
    expect(screen.getByText(dateStr)).toBeInTheDocument();
  });

  it("capitalizes activity type", () => {
    render(
      <ActivityList
        activities={[makeActivity({ type: "BUY" })]}
        loading={false}
      />,
    );
    expect(screen.getByText("Buy")).toBeInTheDocument();
  });

  it("shows dash for null description", () => {
    render(
      <ActivityList
        activities={[makeActivity({ description: null })]}
        loading={false}
      />,
    );
    const cells = screen.getAllByRole("cell");
    const descriptionCell = cells[2]; // Date, Type, Description, Amount
    expect(descriptionCell).toHaveTextContent("-");
  });

  it("shows dash for null amount", () => {
    render(
      <ActivityList
        activities={[makeActivity({ amount: null })]}
        loading={false}
      />,
    );
    const cells = screen.getAllByRole("cell");
    const amountCell = cells[3];
    expect(amountCell).toHaveTextContent("-");
  });

  it("renders positive amounts in green", () => {
    render(
      <ActivityList
        activities={[makeActivity({ amount: "125.50" })]}
        loading={false}
      />,
    );
    const cells = screen.getAllByRole("cell");
    const amountCell = cells[3];
    expect(amountCell).toHaveClass("text-tf-positive");
    expect(amountCell).toHaveTextContent("$125.50");
  });

  it("renders negative amounts in red", () => {
    render(
      <ActivityList
        activities={[makeActivity({ amount: "-500.00" })]}
        loading={false}
      />,
    );
    const cells = screen.getAllByRole("cell");
    const amountCell = cells[3];
    expect(amountCell).toHaveClass("text-tf-negative");
    expect(amountCell).toHaveTextContent("-$500.00");
  });

  it("renders zero amounts in gray", () => {
    render(
      <ActivityList
        activities={[makeActivity({ amount: "0" })]}
        loading={false}
      />,
    );
    const cells = screen.getAllByRole("cell");
    const amountCell = cells[3];
    expect(amountCell).toHaveClass("text-tf-text-tertiary");
  });

  it("renders multiple activities", () => {
    const activities = [
      makeActivity({ id: "act-1", type: "DIVIDEND", amount: "50.00" }),
      makeActivity({ id: "act-2", type: "BUY", amount: "-1000.00" }),
      makeActivity({ id: "act-3", type: "SELL", amount: "2000.00" }),
    ];
    render(<ActivityList activities={activities} loading={false} />);
    const rows = screen.getAllByRole("row");
    // 1 header row + 3 data rows
    expect(rows).toHaveLength(4);
  });
});
